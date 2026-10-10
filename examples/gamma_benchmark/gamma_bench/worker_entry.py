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

"""Load only the harness package into another Python environment.

Adding the controller's site-packages directory to sys.path would accidentally
expose its numerical dependencies to the candidate. Bootstrap the package by
location instead; all third-party imports use the worker interpreter's paths.
"""

from pathlib import Path
import importlib.util
import sys


def main():
    package_directory = Path(__file__).resolve().parent
    if sys.path and Path(sys.path[0]).resolve() == package_directory:
        sys.path.pop(0)
    specification = importlib.util.spec_from_file_location(
        "gamma_bench",
        package_directory / "__init__.py",
        submodule_search_locations=[str(package_directory)],
    )
    package = importlib.util.module_from_spec(specification)
    sys.modules["gamma_bench"] = package
    specification.loader.exec_module(package)
    from gamma_bench.worker import main as worker_main

    return worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
