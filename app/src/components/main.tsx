import React from 'react';

import { Subscription } from 'rxjs';

import {
  FileInput, H1, H2, Button, ProgressBar,
  Drawer
} from '@blueprintjs/core';

import MonacoEditor from 'react-monaco-editor';

import { saveAs } from 'file-saver';

import { AppNavbar } from './navbar';
import { AppText } from './text';
import { AppFileTree } from './file-tree'
import { AppSelectScript } from './select-script'

import {
  pythonReady, pythonData, IPythonData, pythonCode
} from '../observables/python'
import { inputDirectory, outputDirectory } from '../observables/directories'

import runUserCode from '../python/run-user-code.py';
import zipOutput from '../python/zip-output.py';
import updateOutput from '../python/update-output.py';


declare let pyodide: any;
declare var Module: any;


function runConversion() {
  pyodide.runPython(runUserCode)
    .catch(() => {
      pyodide.runPython(updateOutput)
    })
    .then(() => {
      pyodide.runPython(updateOutput)
    })
}

function downloadOutput() {
  pyodide.runPython(zipOutput).then(() => {
    let zip = Module.FS.readFile('/output.zip') as Uint8Array
    saveAs(new Blob([new Uint8Array(zip)]), 'output.zip')
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

interface IAppMainProps {

}

interface IAppMainState extends Readonly<{}> {
  isPythonReady: boolean;
  pythonData: IPythonData;
  codeIsOpen: boolean;
  hasInputFiles: boolean;
  hasOutputFiles: boolean;
}

export class AppMain extends React.Component<IAppMainProps, IAppMainState> {
  subscriptions: Subscription[] = []
  editorSubscription: Subscription | undefined = undefined

  constructor(props: IAppMainProps) {
    super(props)
    this.state = {
      isPythonReady: false,
      pythonData: pythonData.getValue(),
      codeIsOpen: false,
      hasInputFiles: false,
      hasOutputFiles: false
    }
  }

  componentDidMount() {
    this.subscriptions.push(
      pythonReady.subscribe(isPythonReady => {
        this.setState({
          isPythonReady: isPythonReady
        })
      })
    )
    this.subscriptions.push(
      pythonData.subscribe(data => {
        this.setState({
          pythonData: data
        })
      })
    )
    this.subscriptions.push(
      inputDirectory.subscribe(value => {
        this.setState({
          hasInputFiles: value.size !== 0
        })
      })
    )
    this.subscriptions.push(
      outputDirectory.subscribe(value => {
        this.setState({
          hasOutputFiles: value.size !== 0
        })
      })
    )
  }

  componentWillUnmount() {
    this.subscriptions.forEach(subscription => {
      subscription.unsubscribe();
    })
  }

  private showCode = () => this.setState({ codeIsOpen: true });
  private hideCode = () => {
    this.setState({ codeIsOpen: false })
    let editorSubscription = this.editorSubscription as Subscription
    editorSubscription.unsubscribe()
  };

  private editorOnChange(code: string, event: any) {
    pythonCode.next(code)
  }

  private editorDidMount = (editor: any, monaco: any) => {
    editor.value = pythonCode.getValue()
    editor.focus()
    this.editorSubscription = pythonCode.subscribe(value => {
      editor.value = value
    })
  }

  render() {
    return (
      <div className="AppMain">
        <AppNavbar />

        <H1>ALPHA &mdash; PyMedPhys File Processing</H1>
        <AppText />

        <div hidden={this.state.isPythonReady}>
          <H2>Currently Loading Python...</H2>
          <p>Before any file processing begins you need to finish downloading and initialising Python and the required packages.</p>
          <ProgressBar intent="primary" />
        </div>


        <H2>Code to use</H2>

        <AppSelectScript />
        <Button
          intent="primary"
          icon="eye-open"
          rightIcon="edit"
          text="Show and/or edit code" onClick={this.showCode}></Button>

        <Drawer
          onClose={this.hideCode}
          isOpen={this.state.codeIsOpen}
        >
          <div className="monaco-container">
            <MonacoEditor
              language="python" width="100%" height="100%"
              onChange={this.editorOnChange}
              editorDidMount={this.editorDidMount}
              value={pythonCode.getValue()}
            />
          </div>
        </Drawer>

        <H2>File management</H2>

        <div>
          <FileInput inputProps={{ multiple: true }} id="trfFileInput" text="Choose file..." onInputChange={onFileInputChange} disabled={!this.state.isPythonReady} />
        </div>

        <br></br>

        <AppFileTree />

        <H2>File processing</H2>


        <br></br>



        <span className="floatleft">
          <Button
            intent="primary"
            text="Process Files"
            icon="key-enter"
            onClick={runConversion}
            disabled={!this.state.isPythonReady || !this.state.hasInputFiles} />
        </span>
        <span className="floatright">
          <Button
            intent="success"
            text="Save output"
            icon="download"
            onClick={downloadOutput}
            disabled={!this.state.isPythonReady || !this.state.hasOutputFiles} />
        </span>




      </div>
    );
  }
}
