import React from 'react';
import './App.css';

import { FileInput, H2 } from '@blueprintjs/core';

const App: React.FC = () => {
  return (
    <div className="App">
      <H2>Testing trf decoding</H2>
      <p><a href="/data/vmat.trf">Download a demo .trf file</a></p>
      <FileInput text="Choose file..." />
    </div>
  );
}

export default App;
