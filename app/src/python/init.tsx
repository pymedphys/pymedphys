import { BehaviorSubject, Subject } from 'rxjs';

import raw from "raw.macro";

import { wheelsReady, pythonReady } from '../observables/python'
import { inputDirectory, outputDirectory } from '../observables/directories'

declare let pyodide: any;
declare let languagePluginLoader: any;

declare global {
  interface Window {
    wheelsReady: Subject<boolean>;
    inputDirectory: BehaviorSubject<Set<string>>;
    outputDirectory: BehaviorSubject<Set<string>>;
  }
}

window.wheelsReady = wheelsReady;
window.inputDirectory = inputDirectory;
window.outputDirectory = outputDirectory;

pythonReady.subscribe(isPythonReady => {
  console.log(`pythonReady = ${isPythonReady}`)
})

const loadWheels = raw("./load_wheels.py");
const setupDirectories = raw("./setup_directories.py");

export function initPython() {
  languagePluginLoader.then(() => {
    return pyodide.loadPackage(['distlib'])
  }).then(() => {
    return Promise.all([
      // wheelsReady.toPromise(),
      pyodide.runPython(setupDirectories),
      pyodide.runPython(loadWheels),
      pyodide.loadPackage(['matplotlib', 'numpy', 'pandas'])
    ])
  }).then(() => {
    pythonReady.next(true)
  })
}
