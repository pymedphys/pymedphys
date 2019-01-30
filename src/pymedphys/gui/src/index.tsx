import React from 'react';
import ReactDOM from 'react-dom';

import './style.css';
import DollarsTable from './table';

import { dockpanel } from './dockpanel';
import { CodeButtons, createConsole } from './jupyter';

function main() {
  let root = document.getElementById('root') as HTMLDivElement
  dockpanel(root)
  ReactDOM.render(<DollarsTable />, document.getElementById('table'));

  ReactDOM.render(<CodeButtons />, document.getElementById('output'));

  // let outputDiv = document.getElementById('output') as HTMLDivElement
  // matplotlib(outputDiv);

  // let consoleDiv = document.getElementById('console') as HTMLDivElement
  // createConsole(consoleDiv);
}

window.onload = main;
