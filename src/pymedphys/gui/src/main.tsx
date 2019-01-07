import * as React from 'react';
import * as ReactDOM from 'react-dom';

import "./style.scss"
import { matplotlib } from './matplotlib';

import { Cell, Column, Table } from "@blueprintjs/table";

const cellRenderer = (rowIndex: number) => {
  return <Cell>{`$${(rowIndex * 10).toFixed(2)}`}</Cell>
};

const cellRenderer2 = (rowIndex: number) => {
  return <Cell>{`$${(rowIndex * 100).toFixed(2)}`}</Cell>
};

const app = document.getElementById('app') as HTMLDivElement

const root = document.createElement('div')
app.append(root)

ReactDOM.render(
  <Table numRows={10}>
    <Column name="Dollars" cellRenderer={cellRenderer} />
    <Column name="Dollars2" cellRenderer={cellRenderer2} />
  </Table>,
  root
);

matplotlib(app)