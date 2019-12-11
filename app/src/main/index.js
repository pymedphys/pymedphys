'use strict'

import { app, BrowserWindow } from 'electron'
import * as path from 'path'
import { exec } from 'child_process'
import { BehaviorSubject } from 'rxjs'

// global reference to mainWindow (necessary to prevent window from being garbage collected)
let mainWindow
let pythonDir = path.resolve(path.join(__dirname, '..', '..', 'python'))
let pythonExePath = path.join(pythonDir, 'python.exe')

if (process.platform !== "win32") {
  pythonExePath = `wine ${pythonExePath}`
}
console.log(pythonDir)
let pythonServer = exec(`${pythonExePath} -m pymedphys app --no-browser`, { cwd: pythonDir })
let UrlSubject = new BehaviorSubject(null)
pythonServer.stdout.on('data', data => {
  console.log(data)
  UrlSubject.next(data)
})

pythonServer.stderr.on('data', function (data) {
  //throw errors
  console.log('stderr: ' + data);
});

pythonServer.on('close', function (code) {
  console.log('child process exited with code ' + code);
});

function createMainWindow() {
  const window = new BrowserWindow({ webPreferences: { nodeIntegration: true } })

  UrlSubject.subscribe(data => {
    if (data !== null) {
      console.log('boo')
      let data_object = JSON.parse(data)

      let url = data_object['url']

      window.loadURL(url)
    }
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
