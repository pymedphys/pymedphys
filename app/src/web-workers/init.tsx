import PyodideWorker from './pyodide.worker';

import {
  receiverMessengers, senderMessengers,
  sendInitialise
} from '../observables/webworker-messaging';


const pyodideWorker = new PyodideWorker() as Worker

receiverMessengers.base.subscribe(message => {
  console.log("Received main <-- webworker")
  console.log(message)
})

senderMessengers.base.subscribe(message => {
  console.log("Sending main --> webworker")
  console.log(message)
  pyodideWorker.postMessage(message, message.transferables)
})

pyodideWorker.onmessage = (event: MessageEvent) => {
  receiverMessengers.base.next(event.data)
}

export const pyodideInitialise = sendInitialise()
