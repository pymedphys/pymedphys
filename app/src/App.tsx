import React from 'react';

import { Subscription } from 'rxjs';

import { FileInput, H2, Button } from '@blueprintjs/core';

import raw from "raw.macro";
import { saveAs } from 'file-saver';

import './App.css';

import { wheelsReady } from './observables/wheels'
import { inputDirectory, outputDirectory } from './observables/directories'

const decodeTRFPythonCode = raw("./python/decode_trf.py");
declare let pyodide: any;
declare var Module: any;


function runConversion() {
  pyodide.runPythonAsync(decodeTRFPythonCode).then(() => {
    let headerFilepath = pyodide.pyimport("header_filename")
    let tableFilepath = pyodide.pyimport("table_filename")

    let header = Module.FS.readFile(headerFilepath) as Uint8Array
    let table = Module.FS.readFile(tableFilepath) as Uint8Array
    saveAs(new Blob([new Uint8Array(header)]), headerFilepath)
    saveAs(new Blob([new Uint8Array(table)]), tableFilepath)
  })
}

function onFileInputChange(event: React.FormEvent<HTMLInputElement>) {
  let fileInput = event.target as HTMLInputElement;

  let files = fileInput.files as FileList;
  let fileArray = Array.from(files);
  fileInput.value = '';

  fileArray.forEach(file => {
    let fr = new FileReader();
    fr.onload = function () {
      let result = fr.result as ArrayBuffer
      var data = new Uint8Array(result);

      Module['FS_createDataFile']('/input/', file.name, data, true, true, true);
      inputDirectory.next(inputDirectory.getValue().add(file.name))
    };

    fr.readAsArrayBuffer(file);
  })
}


interface AppProps {

}





class App extends React.Component {
  subscription!: Subscription
  state: Readonly<{
    areWheelsReady: boolean
  }>

  constructor(props: AppProps) {
    super(props)
    this.state = {
      areWheelsReady: false
    }
  }

  componentDidMount() {
    this.subscription = wheelsReady.subscribe(areWheelsReady => {
      this.setState({
        areWheelsReady: areWheelsReady
      })
    })
  }

  componentWillUnmount() {
    this.subscription.unsubscribe()
  }

  render() {
    return (
      <div className="App">
        <H2>Testing trf decoding</H2>
        <p><a href="/data/vmat.trf">Download a demo .trf file</a></p>
        <FileInput id="trfFileInput" text="Choose file..." onInputChange={onFileInputChange} />
        <Button icon="refresh" onClick={runConversion} disabled={!this.state.areWheelsReady} />
      </div>
    );
  }
}

export default App;
