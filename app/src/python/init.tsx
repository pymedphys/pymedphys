import { BehaviorSubject } from 'rxjs';

import raw from "raw.macro";

import { wheelsReady } from '../observables/wheels'
import { inputDirectory, outputDirectory } from '../observables/directories'

declare let pyodide: any;
declare let languagePluginLoader: any;

declare global {
  interface Window {
    wheelsReady: BehaviorSubject<boolean>;
    inputDirectory: BehaviorSubject<Set<string>>;
    outputDirectory: BehaviorSubject<Set<string>>;
  }
}

window.wheelsReady = wheelsReady;
window.inputDirectory = inputDirectory;
window.outputDirectory = outputDirectory;

wheelsReady.subscribe(areWheelsReady => {
  console.log(`wheelsReady = ${areWheelsReady}`)
})

const loadWheels = raw("./load_wheels.py");
const setupDirectories = raw("./setup_directories.py");

export function initPython() {
  languagePluginLoader.then(() => {
    return pyodide.loadPackage(['distlib', 'matplotlib', 'numpy', 'pandas'])
  }).then(() => {
    return pyodide.runPythonAsync(loadWheels);
  }).then(() => {
    return pyodide.runPythonAsync(setupDirectories);
  }).then(() => {

  })
}
