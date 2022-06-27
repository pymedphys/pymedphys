# Creating a Streamlit Executable

## Document overview

This document details the process undergone to create an Electron application
that embeds streamlit. The result is an easily shareable binary built for each
of the major operating systems.

This document refers to the state of the PyMedPhys code base as at commit hash
[836f272d092f294099bb51db05bab80d2bfcb628](https://github.com/pymedphys/pymedphys/tree/836f272d092f294099bb51db05bab80d2bfcb628).
All code links will be pointing to the code base at that commit hash.

## Quick version

To actually build and create the PyMedPhys Streamlit binary all you actually
need to do is the following:

- Install [Poetry](https://python-poetry.org/docs/#installation)
- Install [Node](https://nodejs.org/en/) and [Yarn 1.x](https://classic.yarnpkg.com/en/docs/install#debian-stable)
- Install PyOxidizer by installing all the project build dependencies:
  - `poetry install -E build -E cli`
- Then run `poetry run pymedphys dev build --install`
  - Which runs [this](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/lib/pymedphys/_dev/build.py#L28-L51) under the hood.

The final built application for your current OS will be contained within
`js/app/dist`.

If you would like to dig deeper into what the above is doing under the hood, or
you would like to adapt PyMedPhys' approach to your own Streamlit project, then
read on.

## Approach overview

To create this binary build four key steps were undergone:

- Create a completely system independent self contained Python environment
- Set up the electron desktop application wrapper
- Make the desktop application boot and connect to the streamlit running within
  the self contained Python environment.
- Use electron builder to create an installer, run this within GitHub actions
  across the three major OSs.

Further detail into each of these steps along with the corresponding code is
given below. Also, if you'd like help achieving any of this, some details
around that are provided at the end of this document.

## Creating a self contained PyMedPhys python bundle

### Justification

To create the self contained Python environment PyOxidizer was utilised. This
tool contains a range of embeddable Python distributions for each OS. There are
a range of issues with a standard Python install, venv or otherwise, that make
it hard to pick up the Python install off one computer onto another computer in
a portable fashion. One such issue is that the standard Python install
explicitly hardcodes the install location. Therefore, subsequent moving of the
installation causes issues.

There are many tools that can create embedded Python installations. PyInstaller
is one, however I have had issues where it gets flagged as the created program
gets flagged as a virus on Windows. It also, in the name of trying to make a
small install size, by default strips out a lot of dependencies. This
"stripping out" makes the resulting binary have many weird edge case issues.

At the end of the day, the goal was to utilise a tool that creates an embedded
Python distribution that is as close to "standard" as possible. PyOxidizer can
be configured to achieve that, so that was utilised.

### The `pyoxidizer.bzl` configuration file

The configuration file for building the binary can be found at
[pyoxidizer.bzl](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl).

We'll go into the key details that make this configuration file different here.
Further details about the PyOxidizer configuration file can be found in
[the official docs](https://pyoxidizer.readthedocs.io/en/stable/).

PyOxidizer comes with a range of amazing tooling to create custom binaries. We
however will be mostly turning all of this amazing tooling off for maximum
compatibility with a standard Python installation. The key steps are the
following.

#### Files mode

Make resource handling be set to "files" mode (needed for NumPy at least) [#L20](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl#L20)

```python
policy.set_resource_handling_mode("files")
```

#### File system relative resources with site-packages name

Use filesystem-relative for the resource location, and use a filename of "site-packages" [#L22-L24](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl#L22-L24)

```python
policy.resources_location = "filesystem-relative:site-packages"
```

A specific fix for Streamlit is the need to use "site-packages" within the
resource location
([#L22-L27](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl#L22-L27)).
This is due to Streamlit using [that file directory location as an indicator](https://github.com/streamlit/streamlit/blob/953dfdbeb51a4d0cb4ddb81aaad8e4321fe5db73/lib/streamlit/config.py#L255-L267)
that Streamlit is not running in developer mode.

#### Use standard importer

Disable the PyOxidizer importer [#L30-L31](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl#L30-L31)

```python
python_config.filesystem_importer = True
python_config.oxidized_importer = False
```

### Running the build

Once that configuration file is created, and once PyOxidizer is installed then
running `poetry run pyoxidizer build install` will create a `pymedphys` binary
within a `dist` directory within the repository root.

## The use and setting up of Electron

### Justification

Now that we have a self contained PyMedPhys distribution, arguably we could be
done. Also, arguably, bringing in the heavy beast of Electron potentially
complicates things significantly. However, it does have a few benefits. The
primary benefits being that electron builder manages the creation of the
installer as well as management of auto-update capacity, if we want to support
that in the future.

PyOxidizer does also manage the creation of the installer. However, with my
trialling of it in the past this installer was only able to run as
administrator on Windows, which is likely a deal breaker in many scenarios.

Instead of using Electron we could manually handle the installer ourselves. But
then we'd have to do that independently for each OS. By using electron, we can
run the same set up on one OS, and have it automatically create installers on
each target OS with little to no adjustments needed. Having a bulky executable
created at the other side is a reasonable trade off in my opinion for
significantly reduced maintenance burden on PyMedPhys.

### Setting up Electron

To set up the Electron code base I began with the following boilerplate code:

> <https://github.com/szwacz/electron-boilerplate>

I significantly stripped it back so as to include as little as possible while
still having success.

The resulting Electron application code utilised can be found at
[`js/app`](https://github.com/pymedphys/pymedphys/tree/836f272d092f294099bb51db05bab80d2bfcb628/js/app).

To install all of the required dependencies run `yarn install` within the
`js/app` directory. You will need to have both [Node](https://nodejs.org/en/)
and [Yarn 1.x](https://classic.yarnpkg.com/en/docs/install#debian-stable)
installed to achieve this.

### The key components of the Electron code base

Below is a short overview of the key components of the Electron application
code base.

#### The `package.json` file

A resources directory called `python` is selected and included within the
build:

```json
    "directories": {
      "buildResources": "resources"
    },
    "extraResources": [
      {
        "from": "python",
        "to": "python",
        "filter": [
          "**/*"
        ]
      }
    ],
```

> [js/app/package.json#L22-L33](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/js/app/package.json#L22-L33)

This directory doesn't exist in the source tree. When the Electron app is being
built with `poetry run pymedphys dev build` this `python` directory is created
by running `pyoxidizer` and then moving the resulting built distribution over
to `js/app/python`:

```python
PYOXIDIZER_BUILD = REPO_ROOT.joinpath("build")
PYOXIDIZER_DIST = PYOXIDIZER_BUILD.joinpath("dist")

ELECTRON_APP_DIR = REPO_ROOT.joinpath("js", "app")
PYTHON_APP_DESTINATION = ELECTRON_APP_DIR.joinpath("python")

...

    subprocess.check_call(
        ["poetry", "run", "pyoxidizer", "build", "install"], cwd=REPO_ROOT
    )
    shutil.move(PYOXIDIZER_DIST, PYTHON_APP_DESTINATION)
```

> [lib/pymedphys/\_dev/build.py](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/lib/pymedphys/_dev/build.py)

#### The `main.ts` file

Within `main.ts` the streamlit GUI itself is booted from within the above
defined `python` resources directory:

```typescript
appStreamlitServer = spawn("./pymedphys", ["gui", "--electron"], {
  cwd: path.join(process.resourcesPath, "python"),
});
```

> [js/app/src/main.ts#L38-L40](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/js/app/src/main.ts#L38-L40)

And the entire Electron application is really just a light wrapper that opens
up the Streamlit hosted URL:

```typescript
streamlitPortDelegate.promise.then((port) => {
  const pymedphysAppUrl = url.format({
    pathname: `localhost:${port}`,
    protocol: "http:",
    slashes: true,
  });

  mainWindow.loadURL(pymedphysAppUrl);
});
```

> [js/app/src/main.ts#L81-L89](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/js/app/src/main.ts#L81-L89)

So that the Electron app doesn't open the Streamlit webpage before the server
is running, it waits for the Streamlit CLI to print out that the server is
ready:

```typescript
appStreamlitServer.stdout.once("data", (data) => {
  const stdoutJson = JSON.parse(`${data}`);
  const port: string = stdoutJson["port"];

  streamlitPortDelegate.resolve(port);
});
```

> [js/app/src/main.ts#L43-L48](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/js/app/src/main.ts#L43-L48)

## Booting the streamlit app and syncing the port with Electron

When the user starts the application, first the Electron `main.ts` script
starts. This
[spawns the Streamlit GUI](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/js/app/src/main.ts#L38-L40).
Then, the server [waits for a given promise to resolve](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/js/app/src/main.ts#L81) called `streamlitPortDelegate`.
This promise only resolves when the Streamlit CLI prints out a
[specific JSON string](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/js/app/src/main.ts#L43-L48) within the CLI.

However, by default, Streamlit doesn't print the port that it is serving on to
the CLI in such a machine readable format. Instead, it uses a more human
readable approach. As such, the Streamlit package was lightly ["monkey patched"](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/lib/pymedphys/_gui.py#L47-L59)
to print out its utilised port in this JSON format:

```python
def _patch_streamlit_print_url():
    _original_print_url = st.bootstrap._print_url

    def _new_print_url(is_running_hello: bool) -> None:
        port = int(st.config.get_option("browser.serverPort"))

        sys.stdout.flush()
        print(json.dumps({"port": port}))
        sys.stdout.flush()

        _original_print_url(is_running_hello)

    st.bootstrap._print_url = _new_print_url
```

That way, when Streamlit is
serving and ready, the first thing it does is print something like the
following to the CLI:

```json
{ "port": 8051 }
```

This then subsequently triggers the promise within Electron and loads up the
Streamlit URL at the given port (same as copied in from above):

```typescript
streamlitPortDelegate.promise.then((port) => {
  const pymedphysAppUrl = url.format({
    pathname: `localhost:${port}`,
    protocol: "http:",
    slashes: true,
  });

  mainWindow.loadURL(pymedphysAppUrl);
});
```

> [js/app/src/main.ts#L81-L89](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/js/app/src/main.ts#L81-L89)

## Building for all OSs within GitHub Actions

Once the built Streamlit app was up and running on a given OS, then, given the
cross platform nature of the tools utilised, all that was required to create
cross platform installers was to run the binary build across the various
platforms within the CI suite.

The actual build itself was scripted out within the
[PyMedPhys dev CLI](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/lib/pymedphys/_dev/build.py#L16-L51). This was then utilised within the CI:

```yaml
- name: Build Binary
  if: matrix.task == 'build'
  run: |
    poetry run pymedphys dev build --install
```

> [.github/workflows/library.yml#L344-L347](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/.github/workflows/library.yml#L344-L347)

To set up the CI, need to make sure that
[Node, Yarn](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/.github/workflows/library.yml#L244-L250),
[Python](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/.github/workflows/library.yml#L138-L141)
and
[Poetry](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/.github/workflows/library.yml#L173-L187)
were all installed. Needed to also install PyOxidizer, which was included as
PyMedPhys `build` dependency extras. So installation of PyOxidizer and other
CLI dependencies was achieved with [`poetry install -E build -E cli`](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/.github/workflows/library.yml#L306-L311).

Once this build was completed within the CI, the resulting artifacts needed to
be uploaded. That was achieved with:

```yaml
- uses: actions/upload-artifact@v3
  if: matrix.task == 'build'
  with:
    name: PyMedPhysApp-${{ runner.os }}
    path: |
      js/app/dist/*.dmg
      js/app/dist/*.exe
      js/app/dist/*.snap
      js/app/dist/*.AppImage
      !js/app/dist/*unpacked/
```

> [.github/workflows/library.yml#L349-L358](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/.github/workflows/library.yml#L349-L358)

## Getting help

If you'd like to get help with any of the above, or you'd like to use some of
the above to make your own portable Streamlit executables and you're running
into trouble. Feel free to reach out over at the PyMedPhys discourse group
<https://pymedphys.discourse.group/>.
