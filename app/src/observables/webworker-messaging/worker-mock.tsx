import { Subject } from 'rxjs';

import { v4 } from 'uuid';


interface commMock {
  onmessage: ((this: Worker, ev: MessageEvent) => any) | null
  postMessage: (message: any, transfer?: Transferable[] | undefined) => void
}

const workerChannel = new BroadcastChannel('worker');
const mainChannel = new BroadcastChannel('main');
const workerId = v4();

function createWorkerCommMock() {
  const toWorker = new Subject<MessageEvent>()
  const fromWorker = new Subject<MessageEvent>()

  class WorkerMock implements commMock {
    onmessage = (ev: MessageEvent) => { }
    postMessage(ev: MessageEvent, transfer?: Transferable[]) {
      // console.log('Mocked sending worker --> main')
      // console.log(ev)
      workerChannel.postMessage(ev)
    }
    callOnMessage(ev: MessageEvent) {
      // console.log('Mocked receiving worker <-- main')
      // console.log(ev.data)
      this.onmessage(ev)
    }
  }

  const workerMock = new WorkerMock()
  mainChannel.onmessage = message => workerMock.callOnMessage(message)

  class MainMock implements commMock {
    onmessage = (ev: MessageEvent) => { }
    postMessage(ev: MessageEvent, transfer?: Transferable[]) {
      // console.log('Mocked sending main --> worker')
      // console.log(ev)
      mainChannel.postMessage(ev)
    }
    callOnMessage(ev: MessageEvent) {
      // console.log('Mocked receiving main <-- worker')
      // console.log(ev.data)
      this.onmessage(ev)
    }
  }

  const mainMock = new MainMock()
  workerChannel.onmessage = message => mainMock.callOnMessage(message)

  return { workerMock, mainMock }
}

const { workerMock, mainMock } = createWorkerCommMock();

export { workerMock, mainMock }