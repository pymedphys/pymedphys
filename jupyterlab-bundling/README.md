# JupyterLab bundling

Here is a tool which takes as input a directory of Jupyter notebooks as well
as a `requirements.txt` file and it creates `JupyterLab Setup.exe` which will
allow JupyterLab to be installed on another Windows PC. The destination PC
does not need Python or any other dependencies installed. The installation
will include a copy of the Python environment as defined within
`requirements.txt`.

## Usage

Install PyMedPhys:

```bash
pip install pymedphys>=0.17.0
```

Create a `notebooks` directory as well as a `requirements.txt` file, see the
directory that this README is contained within for an example.

Run the following within that directory:

```bash
pymedphys bundle
```

Then, all you should need to do is wait.

## Known bugs

- Current deal breaker bug -- the embedded JupyterLab still uses kernels on the
  local machine.
- Closing the application doesn't actually close the JupyterLab server.
- The created exe is very large, this likely can be reduced by a factor of 2 or
  so, but this isn't a focus at the moment.
  - An easy win here is to install node in another conda environment during
    building, and not actually distributing node in the final exe.
- Icons aren't that of the Jupyter project


## Future features

- Allow customisation of application name
- Allow lab extensions to be declared
- Allow changing of default URL (to handle a different server extension apart
  from JupyterLab)
- Allow defining a version number
- Support `environment.yml` files also
