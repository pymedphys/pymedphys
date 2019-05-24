import './serviceworker.d.ts'

import loadWheels from '../../python/load-wheels.py';
import setupDirectories from '../../python/setup-directories.py';
import setMatplotlibBackend from '../../python/set-matplotlib-backend.py';


interface PyodideWorker extends Worker {
  pyodide: any;
  Module: any;
  languagePluginUrl: string;
}

const ctx: PyodideWorker = self as any;

ctx.languagePluginUrl = 'https://pyodide.pymedphys.com/'
importScripts('https://pyodide.pymedphys.com/pyodide.js')

import {
  receiverMessengers, senderMessengers,
  sendReply, sendFileTransfer
} from './common';

receiverMessengers.base.subscribe(message => {
  console.log("Received webworker <-- main")
  console.log(message)
})

senderMessengers.base.subscribe(message => {
  console.log("Sending webworker --> main")
  console.log(message)
  ctx.postMessage(message, message.transferables)
});

ctx.onmessage = function (e) { // eslint-disable-line no-unused-vars
  receiverMessengers.base.next(e.data)
}

let pythonInitialise = languagePluginLoader.then(() => {
  return Promise.all([
    ctx.pyodide.runPython(setupDirectories),
    ctx.pyodide.runPython(loadWheels),
    ctx.pyodide.loadPackage(['matplotlib', 'numpy', 'pandas'])
  ]).then(() => {
    return ctx.pyodide.runPython(setMatplotlibBackend)
  })
})

receiverMessengers.initialise.subscribe(data => {
  const uuid = data.uuid
  pythonInitialise.then(() => {
    sendReply(uuid, {})
  })
})

function convertCode(code: string) {
  const converted = `
from js import Promise

def run_user_code():
    def run_promise(resolve, reject):
        try:
            exec("""${code}""")
            resolve()
        except Exception as e:
            reject(e)
            raise

    return Promise.new(run_promise)


run_user_code()
`
  console.log(converted)

  return converted
}

receiverMessengers.executeRequest.subscribe(message => {
  const uuid = message.uuid;
  const code = message.data.code;

  pythonInitialise.then(() => {
    pyodide.runPython(convertCode(code))
      .then((result: any) => sendReply(uuid, { result }))
      .catch((error: any) => sendReply(uuid, { error }));
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