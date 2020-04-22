# Streamlit Electron App Bundling (prototype / alpha)

To create your own Streamlit Electron app installer with all of its Python
batteries included into a single installation `setup.exe` run the following
within this directory:

```bash
pip install pymedphys==0.24.1
pymedphys bundle
```

To change the app itself, simply edit `app.py`, to change the dependencies
bundled with the executable edit `requirements.txt`.

## Extra requirements

You will need `yarn` installed on your computer, see
<https://classic.yarnpkg.com/en/docs/install> for how to do that.

You can also create this Windows executable from a Linux machine, to do that,
you will need to have `wine` installed.

## Not yet supported, but planned

* Change version number
* Auto update your app
* Change the apps name
* Add a logo to your app
