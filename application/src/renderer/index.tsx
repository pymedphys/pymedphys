import * as React from 'react';
import * as ReactDOM from 'react-dom';

import * as electron from 'electron';

import "./style.scss"
import { matplotlib } from './matplotlib';

import { Cell, Column, Table } from "@blueprintjs/table";

const cellRenderer = (rowIndex: number) => {
  return <Cell>{`$${(rowIndex * 10).toFixed(2)}`}</Cell>
};

const app = document.getElementById('app') as HTMLDivElement

const root = document.createElement('div')
app.append(root)

ReactDOM.render(
  <Table numRows={10}>
    <Column name="Dollars" cellRenderer={cellRenderer} />
  </Table>,
  root
);

electron.ipcRenderer.on('jupyter', (event: any, store: { port: number; token: string }) => {
  let jupyterConfig = document.createElement('script')
  jupyterConfig.id = 'jupyter-config-data'
  jupyterConfig.type = 'application/json'
  jupyterConfig.textContent = `{ "baseUrl": "http://localhost:${store.port}", "token": "${store.token}" }`
  document.head.append(jupyterConfig)
  matplotlib(app)
})
