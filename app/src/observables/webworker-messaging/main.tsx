// import PyodideWorker from './pyodide.worker';
import { mainMock } from './worker-mock';

import './webworker.tsx'  // Remove this if using webworker

import {
  mainMessengers, IPyodideMessage
} from './common';

const receiverMessengers = mainMessengers.receiver
const senderMessengers = mainMessengers.sender
const sendInitialise = mainMessengers.sendInitialise
const sendExecuteRequest = mainMessengers.sendExecuteRequest
const sendFileTransfer = mainMessengers.sendFileTransfer
const sendFileTransferRequest = mainMessengers.sendFileTransferRequest

let pyodideWorker: Worker
// pyodideWorker = new PyodideWorker() as Worker
pyodideWorker = mainMock as any


receiverMessengers.subscribe((message: IPyodideMessage) => {
  console.log("Received main <-- webworker")
  console.log(message)
})

senderMessengers.subscribe((message: IPyodideMessage) => {
  // console.log("Sending main --> webworker")
  // console.log(message)
  pyodideWorker.postMessage(message, message.transferables)
})

pyodideWorker.onmessage = (event: MessageEvent) => {
  receiverMessengers.next(event.data)
}

const pyodideInitialise = sendInitialise()

export {
  pyodideInitialise, sendExecuteRequest, sendFileTransfer,
  sendFileTransferRequest, receiverMessengers
}