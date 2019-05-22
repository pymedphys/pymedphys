import PyodideWorker from './pyodide.worker.js';

export function runPyodide() {
  const pyodideWorker = new PyodideWorker()

  pyodideWorker.onerror = (e) => {
    console.log(`Error in pyodideWorker at ${e.filename}, Line: ${e.lineno}, ${e.message}`)
  }

  pyodideWorker.onmessage = (e) => {
    const { results, error } = e.data
    if (results) {
      console.log('pyodideWorker return results: ', results)
    } else if (error) {
      console.log('pyodideWorker error: ', error)
    }
  }

  const data = {
    A_rank: [0.8, 0.4, 1.2, 3.7, 2.6, 5.8],
    python:
      'import statistics\n' +
      'from js import A_rank\n' +
      'statistics.stdev(A_rank)'
  }

  pyodideWorker.postMessage(data)
}

