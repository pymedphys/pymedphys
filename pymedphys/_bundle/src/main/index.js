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

let pythonScriptPath = path.resolve(path.join(pythonDir, '..', 'run.py'))

let pythonExePath = path.join(pythonDir, 'python.exe')
let pythonExeCommand

if (process.platform === "win32") {
  pythonExeCommand = `"${pythonExePath}"`
} else {
  pythonExeCommand = `wine "${pythonExePath}"`
}

let toBeRun = `${pythonExeCommand} "${pythonScriptPath}"`
console.log(toBeRun)

let pythonServer = exec(toBeRun)
let UrlSubject = new BehaviorSubject(null)
pythonServer.stdout.on('data', data => {
  console.log('stdout: ' + data);
  UrlSubject.next(data)
})

pythonServer.stderr.on('data', data => {
  console.log('stderr: ' + data);
});

pythonServer.on('close', code => {
  console.log('child process exited with code ' + code);
});

function createMainWindow() {
  const window = new BrowserWindow({ webPreferences: { nodeIntegration: true } })

  UrlSubject.subscribe(data => {
    try {
      const data_object = JSON.parse(data)
      const ip = data_object['ip']
      const port = data_object['port']
      const url = `http://${ip}:${port}`
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
