# Jupyter lab bundling

Here is a tool which takes as input a directory of Jupyter notebooks as well
as a `requirements.txt` file and it creates `JupyterLab Setup.exe` which will
allow JupyterLab to be installed on another Windows PC with an embedded Python
environment and your notebooks.

## Usage

Install pymedphys:

```bash
pip install pymedphys >= 0.17.0
```

Create a notebooks directory as well as a `requirements.txt` file, see this
current directory for examples.

Run the following within that directory:

```bash
pymedphys bundle
```

Then, all you should need to do is wait.

## Known bugs

- Current deal breaker bug -- the embedded JupyterLab still uses kernels on the
  local machine -- oops.
- Closing the application doesn't actually close the JupyterLab server
