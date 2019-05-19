import React from 'react';

import { Subscription } from 'rxjs';

import {
  FileInput, H1, H2, Button, ProgressBar, Classes, Icon, Intent, ITreeNode,
  Position, Tooltip, Tree
} from '@blueprintjs/core';

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



interface AppProps {

}

interface AppState extends Readonly<{}> {
  areWheelsReady: boolean;
  nodes: ITreeNode[];
}

class App extends React.Component {
  subscription!: Subscription
  state: AppState

  constructor(props: AppProps) {
    super(props)
    this.state = {
      areWheelsReady: false,
      nodes: INITIAL_STATE
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
          <FileInput id="trfFileInput" text="Choose file..." onInputChange={onFileInputChange} />
        </div>

        <H2>File processing</H2>
        <div>
          <Button intent="success" text="Process Files" icon="key-enter" onClick={runConversion} disabled={!this.state.areWheelsReady} />
        </div>
      </div>
    );
  }
}

export default App;


/* tslint:disable:object-literal-sort-keys so childNodes can come last */
const INITIAL_STATE: ITreeNode[] = [
  {
    id: 0,
    hasCaret: true,
    icon: "folder-close",
    label: "Folder 0",
  },
  {
    id: 1,
    icon: "folder-close",
    isExpanded: true,
    label: (
      <Tooltip content="I'm a folder <3" position={Position.RIGHT}>
        Folder 1
          </Tooltip>
    ),
    childNodes: [
      {
        id: 2,
        icon: "document",
        label: "Item 0",
        secondaryLabel: (
          <Tooltip content="An eye!">
            <Icon icon="eye-open" />
          </Tooltip>
        ),
      },
      {
        id: 3,
        icon: <Icon icon="tag" intent={Intent.PRIMARY} className={Classes.TREE_NODE_ICON} />,
        label: "Organic meditation gluten-free, sriracha VHS drinking vinegar beard man.",
      },
      {
        id: 4,
        hasCaret: true,
        icon: "folder-close",
        label: (
          <Tooltip content="foo" position={Position.RIGHT}>
            Folder 2
                  </Tooltip>
        ),
        childNodes: [
          { id: 5, label: "No-Icon Item" },
          { id: 6, icon: "tag", label: "Item 1" },
          {
            id: 7,
            hasCaret: true,
            icon: "folder-close",
            label: "Folder 3",
            childNodes: [
              { id: 8, icon: "document", label: "Item 0" },
              { id: 9, icon: "tag", label: "Item 1" },
            ],
          },
        ],
      },
    ],
  },
  {
    id: 2,
    hasCaret: true,
    icon: "folder-close",
    label: "Super secret files",
    disabled: true,
  },
];
/* tslint:enable:object-literal-sort-keys */