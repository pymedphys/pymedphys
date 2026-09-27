# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Subject profiles: the persisted per-subject values.

A subject's date offset, and later its other synthetic values, are
derived when the subject is first exported and persisted in its profile. The
profile is then the single source of truth: it is read back for every later
export, so a change of derivation never silently changes an exported subject.

A store belongs to one key. It records the key's identifier, and each subject
under a keyed token, never under an identifier. Under a project key the
custodian keeps the store with the key, outside output and QC directories;
under an ephemeral key, :meth:`ProfileStore.ephemeral` keeps profiles for the
run only.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import tempfile
from collections.abc import Iterable

from . import dates
from .keys import (
    DERIVATION_VERSION,
    DeidKey,
    custodian_location_problem,
    warn_where_owner_only_modes_are_not_enforced,
)
from .pseudonyms import SubjectIdentity

FORMAT = "pymedphys-deid-profiles/1"
_TOKEN = re.compile("[0-9a-f]{64}")
_PROFILE_FIELDS = frozenset({"date_offset_weeks", "derivation"})


class ProfileError(ValueError):
    """A profile store that cannot be used."""


@dataclasses.dataclass(frozen=True)
class SubjectProfile:
    """The persisted values of one subject.

    Attributes
    ----------
    date_offset_weeks : int
        How far the subject's dates move back, 52 to 520 whole weeks.
    derivation : str
        The derivation version that produced the values, such as
        ``"pymedphys-deid/1"``.
    """

    date_offset_weeks: int
    derivation: str


def _profile_problem(profile: object) -> str | None:
    if not isinstance(profile, dict) or profile.keys() != _PROFILE_FIELDS:
        return "does not have exactly the fields date_offset_weeks and derivation"
    weeks = profile["date_offset_weeks"]
    if (
        isinstance(weeks, bool)
        or not isinstance(weeks, int)
        or not dates.MIN_OFFSET_WEEKS <= weeks <= dates.MAX_OFFSET_WEEKS
    ):
        return "has a date offset that is not 52 to 520 whole weeks"
    derivation = profile["derivation"]
    if not isinstance(derivation, str) or not derivation:
        return "has a derivation that is not non-empty text"
    return None


def _read(path: pathlib.Path, key: DeidKey) -> dict[str, SubjectProfile]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProfileError("the profile store could not be read") from error
    if (
        not isinstance(document, dict)
        or document.keys() != {"format", "key_id", "subjects"}
        or document["format"] != FORMAT
    ):
        raise ProfileError(f"the file is not a {FORMAT} file")
    if document["key_id"] != key.key_id:
        raise ProfileError("the profile store belongs to another key")
    subjects = document["subjects"]
    if not isinstance(subjects, dict):
        raise ProfileError(
            "the store's subjects are not a mapping of tokens to profiles"
        )
    profiles = {}
    for number, (token, profile) in enumerate(subjects.items(), start=1):
        if not _TOKEN.fullmatch(token):
            raise ProfileError(
                f"subject {number} has a subject token that is not 64 hexadecimal digits"
            )
        problem = _profile_problem(profile)
        if problem:
            raise ProfileError(f"subject {number} {problem}")
        profiles[token] = SubjectProfile(**profile)
    return profiles


class ProfileStore:
    """The profiles of the subjects exported under one key.

    Use :meth:`open` for a project key and :meth:`ephemeral` for an
    ephemeral one. One process at a time should use a store: a save replaces
    the whole file, so concurrent writers would lose each other's subjects.
    """

    def __init__(
        self,
        key: DeidKey,
        path: pathlib.Path | None,
        subjects: dict[str, SubjectProfile],
    ) -> None:
        self._key = key
        self._path = path
        self._subjects = subjects

    @classmethod
    def ephemeral(cls, key: DeidKey) -> ProfileStore:
        """Return a store that keeps profiles for this run only."""
        return cls(key, None, {})

    @classmethod
    def open(
        cls,
        key: DeidKey,
        path: str | os.PathLike,
        *,
        protected_dirs: Iterable[str | os.PathLike] = (),
    ) -> ProfileStore:
        """Open the store at ``path``, or start a new one there.

        Parameters
        ----------
        key : DeidKey
            The project key the store belongs to.
        path : str or os.PathLike
            The store, in a location only the custodian can read.
        protected_dirs : iterable of str or os.PathLike, optional
            Directories the store must not be inside, such as a run's output
            and QC directories. The PyMedPhys configuration directory is
            always protected.

        Raises
        ------
        ProfileError
            If ``path`` is inside a protected directory; or if an existing
            store cannot be read, is not a :data:`FORMAT` file, belongs to
            another key, or has a malformed subject token or profile.
        """
        given = pathlib.Path(path).absolute()
        resolved = given.parent.resolve() / given.name
        problem = custodian_location_problem(resolved, protected_dirs)
        if problem:
            raise ProfileError(f"refusing to keep a profile store {problem}")
        subjects = _read(resolved, key) if resolved.exists() else {}
        return cls(key, resolved, subjects)

    def profile(self, identity: SubjectIdentity) -> SubjectProfile:
        """Return the subject's profile, deriving and recording it if new."""
        token = self._key.derive("subject", *identity.parts).hex()
        if token not in self._subjects:
            self._subjects[token] = SubjectProfile(
                date_offset_weeks=dates.date_offset_weeks(self._key, identity),
                derivation=DERIVATION_VERSION.decode("ascii"),
            )
        return self._subjects[token]

    def save(self) -> pathlib.Path:
        """Write the store, replacing the previous version atomically.

        The file is created readable only by its owner where the platform
        enforces file modes; elsewhere a warning says that access depends on
        the directory's access control.

        Raises
        ------
        ProfileError
            If the store is ephemeral.
        """
        if self._path is None:
            raise ProfileError("an ephemeral profile store is never saved")
        text = json.dumps(
            {
                "format": FORMAT,
                "key_id": self._key.key_id,
                "subjects": {
                    token: dataclasses.asdict(profile)
                    for token, profile in sorted(self._subjects.items())
                },
            },
            indent=1,
        )
        # mkstemp creates the file readable and writable only by its owner.
        descriptor, temporary = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".part"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                file.write(text + "\n")
            os.replace(temporary, self._path)
        except BaseException:
            pathlib.Path(temporary).unlink(missing_ok=True)
            raise
        warn_where_owner_only_modes_are_not_enforced("profile store")
        return self._path
