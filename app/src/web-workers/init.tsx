import PyodideWorker from './pyodide.worker';

export function runPyodide() {
  const pyodideWorker = new PyodideWorker()

  pyodideWorker.onmessage = (event: MessageEvent) => {

    console.log('message received')
    console.log(event.data)
  }

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
}

