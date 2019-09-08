import React from 'react';

import { Subscription } from 'rxjs';

import {
  Tree, ITreeNode, Tooltip, Classes, Position
} from '@blueprintjs/core';

import { inputDirectory, outputDirectory } from '../observables/directories'

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

// File tree code copied and modified from:
// https://github.com/palantir/blueprint/blob/06a186c90758bbdca604ed6d7bf639c3d05b1fa0/packages/docs-app/src/examples/core-examples/treeExample.tsx

export interface IAppFileTreeProps {

}


export interface IAppFileTreeState extends Readonly<{}> {
  nodes: ITreeNode[];
}


export class AppFileTree extends React.Component<IAppFileTreeProps, IAppFileTreeState> {
  subscriptions: Subscription[] = [];

  constructor(props: IAppFileTreeProps) {
    super(props)
    this.state = {
      nodes: INITIAL_STATE
    }
  }

  componentDidMount() {
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

  private forEachNode(nodes: ITreeNode[] | undefined, callback: (node: ITreeNode<{}>) => void) {
    if (nodes == null) {
      return;
    }

    for (const node of nodes) {
      callback(node);
      this.forEachNode(node.childNodes, callback);
    }
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


  render() {
    return (
      <Tree
        contents={this.state.nodes}
        onNodeClick={this.handleNodeClick}
        onNodeCollapse={this.handleNodeCollapse}
        onNodeExpand={this.handleNodeExpand}
        className={Classes.ELEVATION_0}
      />
    )
  }
}


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