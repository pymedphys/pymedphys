'use strict'

import { app, BrowserWindow } from 'electron'
import * as path from 'path'
import * as fs from 'fs'
import { exec } from 'child_process'
import { BehaviorSubject } from 'rxjs'

// global reference to mainWindow (necessary to prevent window from being garbage collected)
let mainWindow
let pythonDir = path.resolve(path.join(__dirname, '..', '..', 'python'))

if (!fs.existsSync(pythonDir)) {
  pythonDir = path.resolve(path.join(__dirname, 'python'))
  if (!fs.existsSync(pythonDir)) {
    throw "No Python Directory Found"
  }
}

let notebooksDir = path.resolve(path.join(pythonDir, '..', 'notebooks'))

let pymedphysExePath = path.join(pythonDir, 'Scripts', 'pymedphys.exe')
let pymedphysExeCommand

if (process.platform === "win32") {
  pymedphysExeCommand = pymedphysExePath
} else {
  pymedphysExeCommand = `wine ${pymedphysExePath}`
}

let toBeRun = `${pymedphysExeCommand} jupyterlab ${notebooksDir}`
console.log(toBeRun)

let pythonServer = exec(toBeRun)
let UrlSubject = new BehaviorSubject(null)
pythonServer.stdout.on('data', data => {
  console.log('stdout: ' + data);
  UrlSubject.next(data)
})

pythonServer.stderr.on('data', data => {
  //throw errors
  console.log('stderr: ' + data);
});

pythonServer.on('close', code => {
  console.log('child process exited with code ' + code);
});

function createMainWindow() {
  const window = new BrowserWindow({ webPreferences: { nodeIntegration: true } })

  UrlSubject.subscribe(data => {
    try {
      let data_object = JSON.parse(data)
      let url = data_object['url']
      window.loadURL(url)
    } catch { }
  })

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

// quit application when all windows are closed
app.on('window-all-closed', () => {
  // on macOS it is common for applications to stay open until the user explicitly quits
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('will-quit', () => {
  pythonServer.kill('SIGINT')
})

app.on('activate', () => {
  // on macOS it is common to re-create a window even after all windows have been closed
  if (mainWindow === null) {
    mainWindow = createMainWindow()
  }
})

// create main BrowserWindow when electron is ready
app.on('ready', () => {
  mainWindow = createMainWindow()
})
