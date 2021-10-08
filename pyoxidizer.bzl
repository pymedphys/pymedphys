# Copyright (C) 2021 Radiotherapy AI Pty Ltd

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


def make_exe():
    dist = default_python_distribution(python_version = "3.9")

    policy = dist.make_python_packaging_policy()
    # policy.include_distribution_sources = True
    # policy.include_distribution_resources = True
    # policy.include_file_resources = True
    # policy.include_test = True
    policy.resources_location = "filesystem-relative:lib"

    python_config = dist.make_python_interpreter_config()
    python_config.module_search_paths = ["$ORIGIN/lib"]
    python_config.run_module = "pymedphys"

    exe = dist.to_python_executable(
        name = "pymedphys",
        packaging_policy = policy,
        config = python_config,
    )
    exe.windows_runtime_dlls_mode = "always"
    exe.windows_subsystem = "console"

    # exe.add_python_resources(exe.pip_install(["--use-feature", "in-tree-build", "-r", "requirements-deploy.txt"]))
    exe.add_python_resources(exe.pip_install(["--use-feature", "in-tree-build", "-r", "requirements-cli.txt"]))
    exe.add_python_resources(exe.pip_install(["--use-feature", "in-tree-build", "-r", "requirements-icom.txt"]))
    exe.add_python_resources(exe.pip_install(["."]))

    return exe

def make_embedded_resources(exe):
    return exe.to_embedded_resources()

def make_install(exe):
    # Create an object that represents our installed application file layout.
    files = FileManifest()

    # Add the generated executable to our install layout in the root directory.
    files.add_python_resource(".", exe)

    files.install("dist", replace = True)

    return files

def make_msi(exe):
    # See the full docs for more. But this will convert your Python executable
    # into a `WiXMSIBuilder` Starlark type, which will be converted to a Windows
    # .msi installer when it is built.
    return exe.to_wix_msi_builder(
        # Simple identifier of your app.
        "pymedphys",
        # The name of your application.
        "PyMedPhys",
        # TODO: Propagate this within `pymedphys dev propagate`
        "0.38.0-dev4",
        # The author/manufacturer of your application.
        "PyMedPhys Contributors",
    )

# Tell PyOxidizer about the build targets defined above.
register_target("exe", make_exe)
register_target("resources", make_embedded_resources, depends = ["exe"], default_build_script = True)
register_target("install", make_install, depends = ["exe"])
register_target("msi_installer", make_msi, depends = ["exe"], default = True)

# Resolve whatever targets the invoker of this configuration file is requesting
# be resolved.
resolve_targets()
