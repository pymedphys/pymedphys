import PyodideWorker from './pyodide.worker';

import {
  receiverMessengers, senderMessengers,
  sendInitialise, sendExecuteRequest, sendFileTransfer,
  sendFileTransferRequest, IPyodideMessage
} from './common';


const pyodideWorker = new PyodideWorker() as Worker

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

const pyodideInitialise = sendInitialise()

export {
  pyodideInitialise, sendExecuteRequest, sendFileTransfer,
  sendFileTransferRequest
}