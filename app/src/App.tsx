import React from 'react';

import { Subscription } from 'rxjs';

import {
  FileInput, H1, H2, Button, ProgressBar, Classes, ITreeNode,
  Position, Tooltip, Tree
} from '@blueprintjs/core';

import raw from "raw.macro";
import { saveAs } from 'file-saver';

import './App.css';

import { wheelsReady } from './observables/wheels'
import { inputDirectory, outputDirectory } from './observables/directories'

const decodeTRF = raw("./python/decode_trf.py");
const zipOutput = raw("./python/decode_trf.py");
declare let pyodide: any;
declare var Module: any;


function runConversion() {
  pyodide.runPythonAsync(decodeTRF)
}

function downloadOutput() {
  pyodide.runPythonAsync(zipOutput).then(() => {
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
  areWheelsReady: boolean;
  nodes: ITreeNode[];
}

class App extends React.Component {
  subscriptions: Subscription[] = []
  state: AppState

  constructor(props: AppProps) {
    super(props)
    this.state = {
      areWheelsReady: false,
      nodes: INITIAL_STATE
    }
  }

  componentDidMount() {
    this.subscriptions.push(
      wheelsReady.subscribe(areWheelsReady => {
        this.setState({
          areWheelsReady: areWheelsReady
        })
      })
    )
    this.subscriptions.push(
      inputDirectory.subscribe(filenames => {
        let currentTree = this.state.nodes
        currentTree[0]['childNodes'] = createFileNodes(filenames)
        this.setState({
          nodes: currentTree
        })
      })
    )
    this.subscriptions.push(
      outputDirectory.subscribe(filenames => {
        let currentTree = this.state.nodes
        currentTree[1]['childNodes'] = createFileNodes(filenames)
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
        <H1>Testing trf decoding</H1>

        <div hidden={this.state.areWheelsReady}>
          <H2>Currently Loading Python...</H2>
          <p>Before any file processing begins you need to finish downloading and initialising Python and the required packages.</p>
          <ProgressBar intent="primary" />
        </div>

        <H2>File management</H2>

        <p><a href="/data/vmat.trf">Download a demo .trf file</a></p>

        <Tree
          contents={this.state.nodes}
          onNodeClick={this.handleNodeClick}
          onNodeCollapse={this.handleNodeCollapse}
          onNodeExpand={this.handleNodeExpand}
          className={Classes.ELEVATION_0}
        />

        <div>
          <FileInput id="trfFileInput" text="Choose file..." onInputChange={onFileInputChange} disabled={!this.state.areWheelsReady} />
        </div>

        <H2>File processing</H2>
        <div>
          <Button intent="primary" text="Process Files" icon="key-enter" onClick={runConversion} disabled={!this.state.areWheelsReady} />
        </div>

        <div>
          <Button intent="success" text="Save output" icon="download" onClick={downloadOutput} disabled={!this.state.areWheelsReady} />
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
    )
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
    )
  }
];
/* tslint:enable:object-literal-sort-keys */