import React, { Component } from 'react';
// import ReactDOM from 'react-dom';

import { Button } from "@blueprintjs/core";
import { Cell, Column, Table } from "@blueprintjs/table";

const cellRenderer = (rowIndex: number) => {
  return <Cell>{`$${(rowIndex * 10).toFixed(2)}`}</Cell>
};

const cellRenderer2 = (rowIndex: number) => {
  return <Cell>{`$${(rowIndex * 100).toFixed(2)}`}</Cell>
};

class DollarsTable extends Component {
  render() {
    return (
      <div>
        <Button icon="refresh" intent="danger" text="Reset" />
        <Table numRows={10}>
          <Column name="Dollars" cellRenderer={cellRenderer} />
          <Column name="Dollars2" cellRenderer={cellRenderer2} />
        </Table>
      </div>
    );
  }
}

const root = document.getElementById('root') as HTMLDivElement

export default DollarsTable;
