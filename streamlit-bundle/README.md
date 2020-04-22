# Streamlit Electron App Bundling

To create your own Streamlit Electron app installer with all of its Python
batteries included into a single installation `setup.exe` run the following
within this directory:

```
pip install pymedphys==0.24.0
pymedphys bundle
```

To change the app itself, simply edit `app.py`, to change the dependencies
bundled with the executable edit `requirements.txt`.

## Not yet supported, but planned

* Change version number
* Auto update your app
* Change the apps name
* Add a logo to your app
