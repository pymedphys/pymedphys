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

"""The runs of the synthetic corpus, one module each.

Each module of this package defines ``RUN``, a
:class:`~pymedphys.tests.dicom._corpus_run.CorpusRun`, and
:data:`CORPUS_RUNS` collects them in the order of their module names. An
option's pull request adds its run as a new module, named after the option,
such as ``retain_uids.py``, so that no two such pull requests change the
same file.
"""

import importlib
import pkgutil

from .._corpus_run import CorpusRun


def _collect() -> tuple[CorpusRun, ...]:
    runs = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda each: each.name):
        module = importlib.import_module(f"{__name__}.{info.name}")
        run = getattr(module, "RUN", None)
        if not isinstance(run, CorpusRun):
            raise TypeError(f"{module.__name__} defines no CorpusRun as RUN")
        runs.append(run)
    return tuple(runs)


CORPUS_RUNS: tuple[CorpusRun, ...] = _collect()
