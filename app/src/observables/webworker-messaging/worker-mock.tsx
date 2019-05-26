import { Subject } from 'rxjs';



function createWorkerCommMock() {
  const toWorker = new Subject<MessageEvent>()
  const fromWorker = new Subject<MessageEvent>()

  const workerMock = {
    onmessage: (func: (value: MessageEvent) => void) => toWorker.subscribe(func),
    postMessage: (value: MessageEvent) => fromWorker.next(value)
  }

  const mainMock = {
    onmessage: (func: (value: MessageEvent) => void) => fromWorker.subscribe(func),
    postMessage: (value: MessageEvent) => toWorker.next(value)
  }

  return { workerMock, mainMock }
}

const { workerMock, mainMock } = createWorkerCommMock();

export { workerMock, mainMock }