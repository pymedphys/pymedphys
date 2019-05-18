import React from 'react';
import ReactDOM from 'react-dom';
import './index.css';
import App from './App';
import * as serviceWorker from './serviceWorker';


import {
  Menu, MenuBar, MenuItem
} from 'phosphor-menus';

import {
  Message
} from 'phosphor-messaging';

import {
  TabPanel
} from 'phosphor-tabs';

import {
  Widget
} from 'phosphor-widget';

import './index.css';



declare let pyodide: any;
declare let languagePluginLoader: any;

/*-----------------------------------------------------------------------------
| Copyright (c) 2014-2015, PhosphorJS Contributors
|
| Distributed under the terms of the BSD 3-Clause License.
|
| The full license is in the file LICENSE, distributed with this software.
|----------------------------------------------------------------------------*/




/**
 * Create the example menu bar.
 */
function createMenuBar(): MenuBar {
  let fileMenu = new Menu([
    new MenuItem({
      text: 'New File',
      shortcut: 'Ctrl+N'
    }),
    new MenuItem({
      text: 'Open File',
      shortcut: 'Ctrl+O'
    }),
    new MenuItem({
      text: 'Save File',
      shortcut: 'Ctrl+S'
    }),
    new MenuItem({
      text: 'Save As...',
      shortcut: 'Ctrl+Shift+S',
      disabled: true
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Close File',
      shortcut: 'Ctrl+W'
    }),
    new MenuItem({
      text: 'Close All'
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'More...',
      submenu: new Menu([
        new MenuItem({
          text: 'One'
        }),
        new MenuItem({
          text: 'Two'
        }),
        new MenuItem({
          text: 'Three'
        }),
        new MenuItem({
          text: 'Four'
        })
      ])
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Exit'
    })
  ]);

  let editMenu = new Menu([
    new MenuItem({
      text: '&Undo',
      icon: 'fa fa-undo',
      shortcut: 'Ctrl+Z'
    }),
    new MenuItem({
      text: '&Repeat',
      icon: 'fa fa-repeat',
      shortcut: 'Ctrl+Y',
      disabled: true
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: '&Copy',
      icon: 'fa fa-copy',
      shortcut: 'Ctrl+C'
    }),
    new MenuItem({
      text: 'Cu&t',
      icon: 'fa fa-cut',
      shortcut: 'Ctrl+X'
    }),
    new MenuItem({
      text: '&Paste',
      icon: 'fa fa-paste',
      shortcut: 'Ctrl+V'
    })
  ]);

  let findMenu = new Menu([
    new MenuItem({
      text: 'Find...',
      shortcut: 'Ctrl+F'
    }),
    new MenuItem({
      text: 'Find Next',
      shortcut: 'F3'
    }),
    new MenuItem({
      text: 'Find Previous',
      shortcut: 'Shift+F3'
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Replace...',
      shortcut: 'Ctrl+H'
    }),
    new MenuItem({
      text: 'Replace Next',
      shortcut: 'Ctrl+Shift+H'
    })
  ]);

  let helpMenu = new Menu([
    new MenuItem({
      text: 'Documentation'
    }),
    new MenuItem({
      text: 'About'
    })
  ]);

  return new MenuBar([
    new MenuItem({
      text: 'File',
      submenu: fileMenu
    }),
    new MenuItem({
      text: 'Edit',
      submenu: editMenu
    }),
    new MenuItem({
      text: 'Find',
      submenu: findMenu
    }),
    new MenuItem({
      text: 'View',
      type: MenuItem.Submenu
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Help',
      submenu: helpMenu
    })
  ]);
}


/**
 * Create the example context menu.
 */
function createContextMenu(): Menu {
  return new Menu([
    new MenuItem({
      text: '&Copy',
      icon: 'fa fa-copy',
      shortcut: 'Ctrl+C'
    }),
    new MenuItem({
      text: 'Cu&t',
      icon: 'fa fa-cut',
      shortcut: 'Ctrl+X'
    }),
    new MenuItem({
      text: '&Paste',
      icon: 'fa fa-paste',
      shortcut: 'Ctrl+V'
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: '&New Tab'
    }),
    new MenuItem({
      text: '&Close Tab'
    }),
    new MenuItem({
      type: MenuItem.Check,
      text: '&Save On Exit'
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Task Manager',
      disabled: true
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'More...',
      submenu: new Menu([
        new MenuItem({
          text: 'One'
        }),
        new MenuItem({
          text: 'Two'
        }),
        new MenuItem({
          text: 'Three'
        }),
        new MenuItem({
          text: 'Four'
        })
      ])
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Close',
      icon: 'fa fa-close'
    })
  ]);
}


class TodoWidget extends Widget {

  static createNode(): HTMLElement {
    var node = document.createElement('div');
    var app = document.createElement('div');
    app.className = 'todoapp';
    app.id = 'output'
    node.appendChild(app);
    return node;
  }

  constructor() {
    super();
    this.addClass('TodoWidget');
  }

  protected onUpdateRequest(msg: Message): void {
    // var host = this.node.firstChild as Element;
    // ReactDOM.render(, host);
    ReactDOM.render(<App />, document.getElementById('output'));
  }
}



/**
 * The main application entry point.
 */
function main(): void {
  var contextArea = new TodoWidget();
  contextArea.addClass('ContextArea');
  // contextArea.node.innerHTML = (
  //   '<h2>Notice the menu bar at the top of the document.</h2>' +
  //   '<h2>Right click this panel for a context menu.</h2>' +
  //   '<h3>Clicked Item: <span id="log-span"></span></h3>'
  // );
  contextArea.title.text = 'React';

  var contextMenu = createContextMenu();
  contextArea.node.addEventListener('contextmenu', (event: MouseEvent) => {
    event.preventDefault();
    var x = event.clientX;
    var y = event.clientY;
    contextMenu.popup(x, y);
  });

  var menuBar = createMenuBar();

  var panel = new TabPanel();
  panel.id = 'main';
  panel.addChild(contextArea);

  menuBar.attach(document.body);
  panel.attach(document.body);

  contextArea.update();

  window.onresize = () => { panel.update() };
}




let pythonCode = `
import hashlib
import importlib
import io
import json
from pathlib import Path
import zipfile

from distlib import markers, util, version

from js import Promise, window, XMLHttpRequest, pyodide as js_pyodide
import pyodide


def _nullop(*args):
    return


def get_url(url):
    def run_promise(resolve, reject):
        def callback(data):
            resolve(data)

        _get_url_async(url, callback)

    return Promise.new(run_promise)


def _get_url_async(url, cb):
    req = XMLHttpRequest.new()
    req.open('GET', url, True)
    req.responseType = 'arraybuffer'

    def callback(e):
        if req.readyState == 4:
            cb(io.BytesIO(req.response))

    req.onreadystatechange = callback
    req.send(None)


WHEEL_BASE = Path('/lib/python3.7/site-packages/').parent


def extract_wheel(fd):
    with zipfile.ZipFile(fd) as zf:
        zf.extractall(WHEEL_BASE)

    importlib.invalidate_caches()


def validate_wheel(data, sha256):
    m = hashlib.sha256()
    m.update(data.getvalue())
    if m.hexdigest() != sha256:
        raise ValueError("Contents don't match hash")


def get_package_no_validation(url):
    def do_install(resolve, reject):
        def run_promise(wheel):
            try:
                extract_wheel(wheel)
            except Exception as e:
                reject(str(e))
            else:
                resolve()

        get_url(url).then(run_promise)

    return Promise.new(do_install)


def get_package(url, sha256):
    def do_install(resolve, reject):
        def callback(wheel):
            try:
                validate_wheel(wheel, sha256)
                extract_wheel(wheel)
            except Exception as e:
                reject(str(e))
            else:
                resolve()

        _get_url_async('https://cors-anywhere.herokuapp.com/' + url, callback)
        importlib.invalidate_caches()

    return Promise.new(do_install)


def load_and_copy_wheels():
    def run_promise(resolve, reject):
        def extract_all_wheels(filenames_json):
            filenames = json.load(filenames_json)

            urls = [
                '/python-wheels/{}'.format(filename)
                for filename in filenames
            ]

            promises = []
            for url in urls:
                promises.append(get_package_no_validation(url))

            Promise.all(promises).then(resolve)

        get_url('/python-wheels/filenames.json').then(extract_all_wheels)

    return Promise.new(run_promise)


def something_awesome(*args):
    from pymedphys_dicom.dicom import DicomBase

    dicom = DicomBase.from_dict({
        'Manufacturer': 'PyMedPhys',
        'PatientName': 'Python^Monte'
    })

    dicom.anonymise(inplace=True)

    print(dicom.dataset)


pydicom_data = (
    'https://files.pythonhosted.org/packages/97/ae/93aeb6ba65cf976a23e735e9d32b0d1ffa2797c418f7161300be2ec1f1dd/pydicom-1.2.0-py2.py3-none-any.whl',
    '2132a9b15a927a1c35a757c0bdef30c373c89cc999cf901633dcd0e8bdd22e84'
)

packaging_data = (
    'https://files.pythonhosted.org/packages/91/32/58bc30e646e55eab8b21abf89e353f59c0cc02c417e42929f4a9546e1b1d/packaging-19.0-py2.py3-none-any.whl',
    '9e1cbf8c12b1f1ce0bb5344b8d7ecf66a6f8a6e91bcb0c84593ed6d3ab5c4ab3'
)

get_package(*pydicom_data).then(
    lambda x: get_package(*packaging_data)
).then(
    lambda x: load_and_copy_wheels()
).then(
    something_awesome
)
`
languagePluginLoader.then(() => {
  return pyodide.loadPackage(['distlib', 'matplotlib', 'numpy', 'pandas'])
}).then(() => {
  pyodide.runPython(pythonCode);
})

// If you want your app to work offline and load faster, you can change
// unregister() to register() below. Note this comes with some pitfalls.
// Learn more about service workers: https://bit.ly/CRA-PWA
serviceWorker.unregister();



window.onload = main;