import React, { Component } from 'react';

import { Cell, Column, Table } from "@blueprintjs/table";

import { matplotlib } from './matplotlib';

const cellRenderer = (rowIndex: number) => {
  return <Cell>{`$${(rowIndex * 10).toFixed(2)}`}</Cell>
};

const cellRenderer2 = (rowIndex: number) => {
  return <Cell>{`$${(rowIndex * 100).toFixed(2)}`}</Cell>
};

class App extends Component {
  render() {
    return (
      <Table numRows={10}>
        <Column name="Dollars" cellRenderer={cellRenderer} />
        <Column name="Dollars2" cellRenderer={cellRenderer2} />
      </Table>
    );
  }
}

const root = document.getElementById('root') as HTMLDivElement
matplotlib(root)

export default App;
