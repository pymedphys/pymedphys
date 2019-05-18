import React from 'react';
import './App.css';
import raw from "raw.macro";
import { FileInput, H2 } from '@blueprintjs/core';


const decodeTRFPythonCode = raw("./python/dicom_anonymise.py");
declare let pyodide: any;


function onFileInputChange() {
  window.wheelsPromise.promise.then(() => {
    pyodide.runPython(decodeTRFPythonCode);
  })
}


const App: React.FC = () => {
  return (
    <div className="App">
      <H2>Testing trf decoding</H2>
      <p><a href="/data/vmat.trf">Download a demo .trf file</a></p>
      <FileInput text="Choose file..." onInputChange={onFileInputChange} />
    </div>
  );
}

export default App;
