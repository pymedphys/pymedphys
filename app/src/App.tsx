import React from 'react';

import { Subscription } from 'rxjs';

import {
  FileInput, H1, H2, H3, Button, ProgressBar, Classes, ITreeNode,
  Position, Tooltip, Tree, NumericInput
} from '@blueprintjs/core';

import raw from "raw.macro";
import { saveAs } from 'file-saver';

import './App.css';

import { pythonReady, pythonData, IPythonData } from './observables/python'
import { inputDirectory, outputDirectory } from './observables/directories'

const trf2dcm = raw("./python/trf2dcm.py");
const zipOutput = raw("./python/zip_output.py");
const updateOutput = raw("./python/update_output.py");
declare let pyodide: any;
declare var Module: any;


function runConversion() {
  pyodide.runPython(trf2dcm)
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

/*
 * Copyright 2015 Palantir Technologies, Inc. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// File tree code copied from https://github.com/palantir/blueprint/blob/06a186c90758bbdca604ed6d7bf639c3d05b1fa0/packages/docs-app/src/examples/core-examples/treeExample.tsx


interface AppProps {

}

interface AppState extends Readonly<{}> {
  isPythonReady: boolean;
  nodes: ITreeNode[];
  pythonData: IPythonData;
}

class App extends React.Component {
  subscriptions: Subscription[] = []
  state: AppState

  constructor(props: AppProps) {
    super(props)
    this.state = {
      isPythonReady: false,
      nodes: INITIAL_STATE,
      pythonData: pythonData.getValue()
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
      inputDirectory.subscribe(filenames => {
        let currentTree = this.state.nodes
        currentTree[0].childNodes = createFileNodes(filenames)
        this.setState({
          nodes: currentTree
        })
      })
    )
    this.subscriptions.push(
      outputDirectory.subscribe(filenames => {
        let currentTree = this.state.nodes
        currentTree[1].childNodes = createFileNodes(filenames)
        this.setState({
          nodes: currentTree
        })
      })
    )
  }

  componentWillUnmount() {
    this.subscriptions.forEach(subscription => {
      subscription.unsubscribe();
    })
  }

  private handleNodeClick = (nodeData: ITreeNode, _nodePath: number[], e: React.MouseEvent<HTMLElement>) => {
    const originallySelected = nodeData.isSelected;
    if (!e.shiftKey) {
      this.forEachNode(this.state.nodes, n => (n.isSelected = false));
    }
    nodeData.isSelected = originallySelected == null ? true : !originallySelected;
    this.setState(this.state);
  };

  private handleNodeCollapse = (nodeData: ITreeNode) => {
    nodeData.isExpanded = false;
    this.setState(this.state);
  };

  private handleNodeExpand = (nodeData: ITreeNode) => {
    nodeData.isExpanded = true;
    this.setState(this.state);
  };

  private forEachNode(nodes: ITreeNode[] | undefined, callback: (node: ITreeNode<{}>) => void) {
    if (nodes == null) {
      return;
    }

    for (const node of nodes) {
      callback(node);
      this.forEachNode(node.childNodes, callback);
    }
  }

  render() {
    return (
      <div className="App">
        <H1>ALPHA &mdash; PyMedPhys File Processing App</H1>

        <H2>Overview</H2>

        <H3>Aim of application</H3>
        <p>
          In its current form this application takes a single Elekta Linac trf
          logfile as well as a single RT DICOM plan file that corresponds to
          the same plan as the logfile. It then process this data and creates
          the following:
        </p>
        <ul>
          <li>Decoded header and table csv files for the logfile</li>
          <li>
            The logfile mapped to a RT DICOM plan file using the provided
            DICOM file as a template (in ALPHA)
          </li>
          <li>
            A plot of the MU Density comparison between the logfile and the
            provided DICOM file
          </li>
        </ul>
        <p>
          In its current form only one Gantry angle is used within the DICOM
          file.
        </p>
        <p>
          In the future it is expected that this application will be able to
          serve as a generic file processing application for a range processing
          tasks.
        </p>

        <H3>Dependencies used</H3>
        <p>
          This is an example application that
          combines <a href="https://github.com/pymedphys/pymedphys/">
            PyMedPhys
          </a> with <a href="https://github.com/iodide-project/pyodide">
            pyodide
          </a>.
        </p>
        <p>
          This application loads Python into the <a href="https://webassembly.org/">
            wasm virtual machine
          </a> of your
          browser allowing Python code to be run on your local machine without
          having Python installed, or without needing Python to run on a remote
          server.
        </p>
        <p>
          When it comes to sensitive information or large data files, this
          means no data needs to leave your computer, while you still get the
          convenience a web app brings in not needing to install anything on
          your PC.
        </p>
        <p>
          Expect this application to freeze up, and not always work as
          expected. Both the application itself, and a key part of
          the engine that makes it work is under very much an ALPHA level of
          release. In practice this means feel free to use this application
          as a means to investigate what is possible, but do not rely on it
          to work correctly, or work at all.
        </p>

        <H2>Instructions for use</H2>
        <p>
          To begin, download the demo .trf and .dcm files using the links
          below:
        </p>
        <ul>
          <li>
            A demo RT DICOM plan
            file &mdash; <a href="/data/RP.2.16.840.1.114337.1.1.1548043901.0_Anonymised.dcm">
              RP.2.16.840.1.114337.1.1.1548043901.0_Anonymised.dcm
            </a>
          </li>
          <li>
            A demo .trf file from the delivery given by the above RT DICOM
            plan &mdash; <a href="/data/imrt.trf">
              imrt.trf
            </a>
          </li>
        </ul>
        <p>
          Then, press browse below under File Management and select the .trf
          and .dcm files.
        </p>
        <p>
          Once these files have appeared within the input directory displayed
          then press "Process Files". At this point in time, unfortunately,
          the application will freeze until the processing is complete.
        </p>
        <p>
          Once the processing is complete, and the files appear within the
          output directory, press "Save Output" to download a zip of the
          contents of the output directory.
        </p>

        <div hidden={this.state.isPythonReady}>
          <H2>Currently Loading Python...</H2>
          <p>Before any file processing begins you need to finish downloading and initialising Python and the required packages.</p>
          <ProgressBar intent="primary" />
        </div>

        <H2>File management</H2>

        <div>
          <FileInput inputProps={{ multiple: true }} id="trfFileInput" text="Choose file..." onInputChange={onFileInputChange} disabled={!this.state.isPythonReady} />
        </div>

        <br></br>

        <Tree
          contents={this.state.nodes}
          onNodeClick={this.handleNodeClick}
          onNodeCollapse={this.handleNodeCollapse}
          onNodeExpand={this.handleNodeExpand}
          className={Classes.ELEVATION_0}
        />

        <H2>File processing</H2>

        Gantry angle to use: <NumericInput value={this.state.pythonData.gantryAngle}></NumericInput>

        <br></br>

        <span className="floatleft">
          <Button
            intent="primary"
            text="Process Files"
            icon="key-enter"
            onClick={runConversion}
            disabled={!this.state.isPythonReady || this.state.nodes[0].childNodes === undefined || this.state.nodes[0].childNodes.length === 0} />
        </span>
        <span className="floatright">
          <Button
            intent="success"
            text="Save output"
            icon="download"
            onClick={downloadOutput}
            disabled={!this.state.isPythonReady || this.state.nodes[1].childNodes === undefined || this.state.nodes[1].childNodes.length === 0} />
        </span>

        <div className="big-top-margin">
          <a href="https://www.netlify.com">
            <img
              alt="Build, deploy, and manage modern web projects"
              src="https://www.netlify.com/img/global/badges/netlify-light.svg">
            </img>
          </a>
        </div>
      </div>
    );
  }
}

export default App;




function createFileNodes(filenames: Set<string>): ITreeNode[] {
  let nodes: ITreeNode[] = [];
  let id = 0
  filenames.forEach(filename => {
    nodes.push(
      {
        id: id++,
        icon: "document",
        label: filename
      }
    )
  })

  return nodes
}


/* tslint:disable:object-literal-sort-keys so childNodes can come last */
const INITIAL_STATE: ITreeNode[] = [
  {
    id: 0,
    hasCaret: true,
    icon: "folder-close",
    isExpanded: true,
    label: (
      <Tooltip content="Provided files go here" position={Position.RIGHT}>
        input
      </Tooltip>
    ),
    childNodes: []
  },
  {
    id: 1,
    hasCaret: true,
    icon: "folder-close",
    isExpanded: true,
    label: (
      <Tooltip content="Processed files go here" position={Position.RIGHT}>
        output
      </Tooltip>
    ),
    childNodes: []
  }
];
/* tslint:enable:object-literal-sort-keys */