import { Subject } from 'rxjs';


interface commMock {
  onmessage: ((this: Worker, ev: MessageEvent) => any) | null
  postMessage: (message: any, transfer?: Transferable[] | undefined) => void
}


function createWorkerCommMock() {
  const toWorker = new Subject<MessageEvent>()
  const fromWorker = new Subject<MessageEvent>()

  class WorkerMock implements commMock {
    onmessage = (ev: MessageEvent) => { }
    postMessage(ev: MessageEvent, transfer?: Transferable[]) {
      // console.log('Mocked sending worker --> main')
      // console.log(ev)
      fromWorker.next({ data: ev } as any)
    }
    callOnMessage(ev: MessageEvent) {
      // console.log('Mocked receiving worker <-- main')
      // console.log(ev.data)
      this.onmessage(ev)
    }
  }

  const workerMock = new WorkerMock()
  toWorker.subscribe((ev: MessageEvent) => {
    workerMock.callOnMessage(ev)
  })

  class MainMock implements commMock {
    onmessage = (ev: MessageEvent) => { }
    postMessage(ev: MessageEvent, transfer?: Transferable[]) {
      // console.log('Mocked sending main --> worker')
      // console.log(ev)
      toWorker.next({ data: ev } as any)
    }
    callOnMessage(ev: MessageEvent) {
      // console.log('Mocked receiving main <-- worker')
      // console.log(ev.data)
      this.onmessage(ev)
    }
  }

  const mainMock = new MainMock()
  fromWorker.subscribe((ev: MessageEvent) => {
    mainMock.callOnMessage(ev)
  })

  return { workerMock, mainMock }
}

const { workerMock, mainMock } = createWorkerCommMock();

export { workerMock, mainMock }