import React from 'react';
import ReactDOM from 'react-dom';

import './style.css';
import DollarsTable from './table';

import { dockpanel } from './dockpanel';
import { matplotlib, createConsole } from './jupyter';

function main() {
  dockpanel()
  ReactDOM.render(<DollarsTable />, document.getElementById('table'));
  document.getElementById('console')

  let outputDiv = document.getElementById('output') as HTMLDivElement
  matplotlib(outputDiv);

  let consoleDiv = document.getElementById('console') as HTMLDivElement
  createConsole(consoleDiv);
}

window.onload = main;
