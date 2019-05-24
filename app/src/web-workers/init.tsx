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
  pyodideWorker.postMessage(message)
})

pyodideWorker.onmessage = (event: MessageEvent) => {
  receiverMessengers.base.next(event.data)
}

export const pyodideInitialise = sendInitialise()


  // pyodideWorker.onerror = (e: any) => {
  //   console.log(`Error in pyodideWorker at ${e.filename}, Line: ${e.lineno}, ${e.message}`)
  // }

  // pyodideWorker.onmessage = (e: any) => {
  //   const { results, error } = e.data
  //   if (results) {
  //     console.log('pyodideWorker return results: ', results)
  //   } else if (error) {
  //     console.log('pyodideWorker error: ', error)
  //   }
  // }

  // const data = {
  //   A_rank: [0.8, 0.4, 1.2, 3.7, 2.6, 5.8],
  //   python:
  //     'import statistics\n' +
  //     'from js import A_rank\n' +
  //     'statistics.stdev(A_rank)'
  // }

  // pyodideWorker.postMessage(data)
// }

