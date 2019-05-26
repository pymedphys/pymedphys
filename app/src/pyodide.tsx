import { pythonReady } from './observables/python';
import { pyodideInitialise } from './observables/webworker-messaging/main';

export function startPyodide() {
  pythonReady.subscribe(isReady => {
    if (isReady) {
      console.log("Python Ready")
    }
  })

  pyodideInitialise.subscribe(() => {
    pythonReady.next(true)
  })
}


