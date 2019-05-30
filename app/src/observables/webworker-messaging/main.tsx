import { mainMock } from './worker-mock';

import {
  mainMessengers, IPyodideMessage
} from './common';

import { pythonReady } from '../python';

const receiverMessengers = mainMessengers.receiver
const senderMessengers = mainMessengers.sender
const sendInitialise = mainMessengers.sendInitialise
const sendExecuteRequest = mainMessengers.sendExecuteRequest
const sendFileTransfer = mainMessengers.sendFileTransfer
const sendFileTransferRequest = mainMessengers.sendFileTransferRequest

let pyodideWorker: Worker
pyodideWorker = mainMock as any


const hookInMain = () => {
  receiverMessengers.subscribe((message: IPyodideMessage) => {
    console.log("Received main <-- webworker")
    console.log(message)
  })

  senderMessengers.subscribe((message: IPyodideMessage) => {
    console.log("Sending main --> webworker")
    console.log(message)
    pyodideWorker.postMessage(message, message.transferables)
  })

  pyodideWorker.onmessage = (event: MessageEvent) => {
    receiverMessengers.next(event.data)
  }
}


const startPyodide = () => {
  pythonReady.subscribe(isReady => {
    if (isReady) {
      console.log("Python Ready")
    }
  })

  sendInitialise().subscribe(() => {
    pythonReady.next(true)
  })
}



export {
  startPyodide, hookInMain, sendInitialise, sendExecuteRequest, sendFileTransfer,
  sendFileTransferRequest, receiverMessengers
}