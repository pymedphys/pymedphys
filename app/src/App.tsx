import React from 'react';
import './App.css';
import raw from "raw.macro";
import { FileInput, H2 } from '@blueprintjs/core';
import { saveAs } from 'file-saver';


const decodeTRFPythonCode = raw("./python/decode_trf.py");
declare let pyodide: any;
declare var Module: any;



function onFileInputChange(event: React.FormEvent<HTMLInputElement>) {
  let fileInput = event.target as HTMLInputElement;

  window.wheelsPromise.promise.then(() => {
    let files = fileInput.files as FileList;
    let fileArray = Array.from(files);
    fileInput.value = '';

    fileArray.forEach(file => {
      let fr = new FileReader();
      fr.onload = function () {
        let result = fr.result as ArrayBuffer
        var data = new Uint8Array(result);

        Module['FS_createDataFile']('/', file.name, data, true, true, true);
        pyodide.runPythonAsync(decodeTRFPythonCode).then(() => {
          let headerFilepath = pyodide.pyimport("header_filename")
          let tableFilepath = pyodide.pyimport("table_filename")


          let header = Module.FS.readFile(headerFilepath) as Uint8Array
          let table = Module.FS.readFile(tableFilepath) as Uint8Array
          saveAs(new Blob([new Uint8Array(header)]), headerFilepath)
          saveAs(new Blob([new Uint8Array(table)]), tableFilepath)
        })
      };

      fr.readAsArrayBuffer(file);
    })

  })
}


const App: React.FC = () => {
  return (
    <div className="App">
      <H2>Testing trf decoding</H2>
      <p><a href="/data/vmat.trf">Download a demo .trf file</a></p>
      <FileInput id="trfFileInput" text="Choose file..." onInputChange={onFileInputChange} />
    </div>
  );
}

export default App;
