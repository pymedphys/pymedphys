import loadWheels from '../../python/load-wheels.py';
import setupDirectories from '../../python/setup-directories.py';

import { usingWebworkers } from './config';
import { workerMock } from './worker-mock';

interface PyodideWorker extends Worker {
  pyodide: any;
  Module: any;
  languagePluginUrl: string;
  document: any;
}

import {
  workerMessengers, IPyodideMessage
} from './common';

const receiverMessengers = workerMessengers.receiver
const senderMessengers = workerMessengers.sender
const sendReply = workerMessengers.sendReply
const sendFileTransfer = workerMessengers.sendFileTransfer

let ctx: PyodideWorker

if (usingWebworkers) {
  ctx = self as any;
  ctx.languagePluginUrl = 'https://pyodide.pymedphys.com/'
  importScripts('https://pyodide.pymedphys.com/pyodide.js')
} else {
  const retypedSelf = self as any;

  ctx = workerMock as any;
  ctx.pyodide = retypedSelf.pyodide;
  ctx.Module = retypedSelf.Module
}

receiverMessengers.subscribe((message: IPyodideMessage) => {
  console.log("Received webworker <-- main")
  console.log(message)
})

senderMessengers.subscribe((message: IPyodideMessage) => {
  console.log("Sending webworker --> main")
  console.log(message)
  ctx.postMessage(message, message.transferables)
});

ctx.onmessage = function (e) { // eslint-disable-line no-unused-vars
  receiverMessengers.next(e.data)
}

let pythonInitialise = languagePluginLoader.then(() => {
  return Promise.all([
    ctx.pyodide.runPython(setupDirectories),
    ctx.pyodide.runPython(loadWheels),
    ctx.pyodide.loadPackage(['matplotlib', 'numpy', 'pandas'])
  ])
})

receiverMessengers.initialise.subscribe(data => {
  const uuid = data.uuid
  pythonInitialise.then(() => {
    sendReply(uuid, {})
  })
})

receiverMessengers.executeRequest.subscribe(message => {
  const uuid = message.uuid;
  const code = message.data.code;

  pythonInitialise.then(() => {
    pyodide.runPythonAsync(code)
      .then((result: any) => {
        sendReply(uuid, { result })
      })
      .catch((error: any) => {
        sendReply(uuid, { error })
      });
  });
})

receiverMessengers.fileTransferRequest.subscribe(message => {
  const uuid = message.uuid
  const filepath = message.data.filepath

  let file: ArrayBuffer = ctx.Module.FS.readFile(filepath)
  sendFileTransfer(file, filepath, uuid)
})

function dirBasenameSplit(filepath: string) {
  const split = filepath.split('/')
  const basename = split[split.length - 1]
  const dir = split.slice(0, -1).join('/') + '/'
  const dirbasename = [dir, basename]

  return dirbasename
}

receiverMessengers.fileTransfer.subscribe(message => {
  const uuid = message.uuid
  const filepath = message.data.filepath
  const file = message.data.file

  if (filepath !== undefined) {
    const dirbasename = dirBasenameSplit(filepath)
    const data = new Uint8Array(file);
    ctx.Module['FS_createDataFile'](dirbasename[0], dirbasename[1], data, true, true, true);

    sendReply(uuid, { result: dirbasename[1] })
  }
})