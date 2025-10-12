# pymedphys/_dvh/audit.py
"""
Audit scaffolding for DVH runs.

Captures:
- Timestamp, host, user
- Python & selected package versions
- Git commit/dirty state (if repository available)
- Input file metadata (path, size, SHA256)
- DVHConfig (as dict)
- Optional extra fields (free-form), e.g. CLI, reference dose, etc.

The record is JSON-serialisable and designed to be persisted next to DVH outputs.
This meets the reproducibility requirements in the Sprint plan.

Notes
-----
We avoid heavy imports (e.g., pydicom) in Sprint 0; SOPInstanceUID extraction,
CT/STRUCT binding, and richer DICOM metadata can be added in Sprint 1–2.

Literature motivation: inter-system DVH variability and implementation choices
(end-caps, sampling, binning) can materially shift metrics — provenance matters.
See the attached DVH plan and cited works for context.  # docs reference only
"""

from __future__ import annotations

import dataclasses
import getpass
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import DVHConfig

# ---------------- helpers ---------------- #


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe_version(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "not-installed"
    except Exception:  # pragma: no cover
        return "unknown"


def _git_info(start: Optional[Path] = None) -> Dict[str, Optional[str]]:
    """
    Best-effort Git provenance: commit, branch, is_dirty.

    Returns a small dict; values may be None if not a git repo or if git is absent.
    """
    start = Path(start or Path.cwd())

    def _run(args: List[str]) -> Optional[str]:
        try:
            return (
                subprocess.check_output(args, cwd=start, stderr=subprocess.DEVNULL)
                .decode()
                .strip()
                or None
            )
        except Exception:
            return None

    commit = _run(["git", "rev-parse", "HEAD"])
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    status = _run(["git", "status", "--porcelain"])
    is_dirty = None
    if status is not None:
        is_dirty = "true" if status.strip() else "false"
    return {"commit": commit, "branch": branch, "dirty": is_dirty}


def _hash_file(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------- models ---------------- #


@dataclass(slots=True)
class InputFileAudit:
    path: str
    size_bytes: int
    sha256: str

    @classmethod
    def from_path(cls, p: Path) -> "InputFileAudit":
        p = Path(p)
        return cls(path=str(p), size_bytes=p.stat().st_size, sha256=_hash_file(p))


@dataclass(slots=True)
class AuditRecord:
    timestamp_utc: str
    hostname: str
    user: str
    platform: str
    python_version: str
    package_versions: Dict[str, str]
    git: Dict[str, Optional[str]]
    config: Dict[str, object]
    inputs: List[InputFileAudit]
    extra: Dict[str, object]

    def to_json(self, indent: int = 2) -> str:
        d = asdict(self)
        return json.dumps(d, indent=indent, sort_keys=True)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path


# ---------------- public API ---------------- #


def build_audit(
    config: DVHConfig,
    input_paths: Iterable[str | os.PathLike[str]] = (),
    extra: Optional[Dict[str, object]] = None,
) -> AuditRecord:
    """
    Create an AuditRecord for a DVH run.

    Parameters
    ----------
    config : DVHConfig
        The configuration used for the run.
    input_paths : Iterable[str | Path]
        File paths to hash (e.g., RTSTRUCT, RTDOSE, CT directory samples).
    extra : Optional[Dict[str, object]]
        Free-form additional context (CLI args, reference dose, structure name).

    Returns
    -------
    AuditRecord
        Serialisable record suitable for persistence next to outputs.

    Examples
    --------
    >>> from pathlib import Path
    >>> from pymedphys._dvh.config import DVHConfig
    >>> rec = build_audit(DVHConfig.preset("clinical_qa"), ["example.dcm"], {"structure": "PTV_66"})
    >>> isinstance(rec.to_json(), str)
    True
    """
    inputs: List[InputFileAudit] = []
    for p in input_paths:
        pp = Path(p)
        if pp.is_file():
            inputs.append(InputFileAudit.from_path(pp))
        elif pp.is_dir():
            # Hash directory by a stable combination of file hashes (Sprint 0: keep simple)
            for child in sorted(pp.rglob("*")):
                if child.is_file():
                    inputs.append(InputFileAudit.from_path(child))
        else:
            # non-existent path is still recorded (size 0, sha "NA") to aid debugging
            inputs.append(InputFileAudit(path=str(pp), size_bytes=0, sha256="NA"))  # type: ignore[arg-type]

    packages = {
        "pymedphys": _safe_version("pymedphys"),
        "numpy": _safe_version("numpy"),
        "scipy": _safe_version("scipy"),
        "pydicom": _safe_version("pydicom"),
    }

    record = AuditRecord(
        timestamp_utc=_iso_now(),
        hostname=socket.gethostname(),
        user=getpass.getuser(),
        platform=platform.platform(),
        python_version=sys.version.split()[0],
        package_versions=packages,
        git=_git_info(),
        config=config.to_dict(),
        inputs=inputs,
        extra=extra or {},
    )
    return record


__all__ = ["AuditRecord", "InputFileAudit", "build_audit"]
