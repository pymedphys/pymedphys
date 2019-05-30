import { v4 } from 'uuid';

import { workerChannel, mainChannel } from './broadcast-channels';

interface commMock {
  onmessage: ((this: Worker, ev: MessageEvent) => any) | null
  postMessage: (message: any, transfer?: Transferable[] | undefined) => void
}

const workerId = v4();

function createWorkerCommMock() {
  class WorkerMock implements commMock {
    onmessage = (ev: MessageEvent) => { }
    postMessage(ev: MessageEvent, transfer?: Transferable[]) {
      workerChannel.postMessage(ev)
    }
    callOnMessage(ev: MessageEvent) {
      this.onmessage(ev)
    }
  }

  const workerMock = new WorkerMock()
  mainChannel.onmessage = message => workerMock.callOnMessage(message)

  class MainMock implements commMock {
    onmessage = (ev: MessageEvent) => { }
    postMessage(ev: MessageEvent, transfer?: Transferable[]) {
      mainChannel.postMessage(ev)
    }
    callOnMessage(ev: MessageEvent) {
      this.onmessage(ev)
    }
  }

  const mainMock = new MainMock()
  workerChannel.onmessage = message => mainMock.callOnMessage(message)

  return { workerMock, mainMock }
}

const { workerMock, mainMock } = createWorkerCommMock();

export { workerMock, mainMock }