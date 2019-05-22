import { BehaviorSubject } from 'rxjs';

import {
  pythonReady, IPythonData, pythonData, pythonCode
} from '../observables/python';
// import { inputDirectory, outputDirectory } from '../observables/directories';

import loadWheels from './load-wheels.py';
import setupDirectories from './setup-directories.py';

declare let pyodide: any;
declare let languagePluginLoader: any;

// declare global {
//   interface Window {
//     pythonData: BehaviorSubject<IPythonData>;
//     pythonCode: BehaviorSubject<string>;
//     inputDirectory: BehaviorSubject<Set<string>>;
//     outputDirectory: BehaviorSubject<Set<string>>;
//   }
// }

// window.pythonData = pythonData;
// window.pythonCode = pythonCode;
// window.inputDirectory = inputDirectory;
// window.outputDirectory = outputDirectory;

pythonReady.subscribe(isPythonReady => {
  console.log(`pythonReady = ${isPythonReady}`)
})

export function initPython() {
  languagePluginLoader.then(() => {
    return pyodide.loadPackage(['distlib'])
  }).then(() => {
    return Promise.all([
      pyodide.runPython(setupDirectories),
      pyodide.runPython(loadWheels),
      pyodide.loadPackage(['matplotlib', 'numpy', 'pandas'])
    ])
  }).then(() => {
    pythonReady.next(true)
  })
}
