'use strict'

import { app, BrowserWindow } from 'electron'
import * as path from 'path'
import * as fs from 'fs';
import * as util from 'util';
import * as child_process from 'child_process';
import { format as formatUrl } from 'url'

const isDevelopment = process.env.NODE_ENV !== 'production'

// global reference to mainWindow (necessary to prevent window from being garbage collected)
let mainWindow: any

function createMainWindow() {
  const window = new BrowserWindow()

  if (isDevelopment) {
    window.webContents.openDevTools()

    const reactDevTools = [
      '/home/simon/.config/google-chrome/Default/Extensions/fmkadmapgofadopljbjfkapdkoienihi/3.4.3_0'
    ]

    reactDevTools.forEach(path => {
      if (fs.existsSync(path)) {
        BrowserWindow.addDevToolsExtension(path)
      }
    });
    window.loadURL(`http://localhost:${process.env.ELECTRON_WEBPACK_WDS_PORT}`)
  }
  else {
    window.loadURL(formatUrl({
      pathname: path.join(__dirname, 'index.html'),
      protocol: 'file',
      slashes: true
    }))
  }

  window.on('closed', () => {
    mainWindow = null
  })

  window.webContents.on('devtools-opened', () => {
    window.focus()
    setImmediate(() => {
      window.focus()
    })
  })

  return window
}

function runJupyterServer(port: number) {
  let exec = util.promisify(child_process.exec);

  let labPromise: Promise<string>
  let and: string
  let bash: string
  let activate: string
  let quote: string
  let start: string

  if (process.platform === 'win32') {
    and = '&';
    bash = 'cmd /C';
    activate = 'activate';
    quote = '';
    start = 'start ';
  } else {
    and = '&&';
    bash = 'bash -c'
    activate = 'source activate';
    quote = "'";
    start = ''
  }

  const begin = `${bash} ${quote}${activate} pymedphys ${and}`

  labPromise = exec(
    `conda env update -f environment.yml ${and} ${begin} python -m ipykernel install --user --name PyMedPhys${quote}`
  ).then(() => {
    return exec(
      `${begin} python -c "import secrets; print(secrets.token_hex(50))"${quote}`
    )
  }).then(value => {
    let token = value.stdout;
    return token
  }).then(token => {
    exec(
      `${begin} ${start}jupyter lab --port ${port} --no-browser --port-retries 0 --LabApp.token=${token}${quote}`
    );
    return token
  })

  labPromise.then(token => {
    console.log(`JupyterLab server running at:\n    http://localhost:${port}/lab?token=${token}`)
  })

  return labPromise
}

// quit application when all windows are closed
app.on('window-all-closed', () => {
  // on macOS it is common for applications to stay open until the user explicitly quits
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  // on macOS it is common to re-create a window even after all windows have been closed
  if (mainWindow === null) {
    mainWindow = createMainWindow()
  }
})

// create main BrowserWindow when electron is ready
app.on('ready', () => {
  const port = 31210
  const labPromise = runJupyterServer(port)
  mainWindow = createMainWindow()

  labPromise.then(token => {
    mainWindow.webContents.send('jupyter', { port, token });
  })
})