import React from 'react';
import ReactDOM from 'react-dom';

import * as serviceWorker from './serviceWorker';

import {
  pythonReady
} from './observables/python';

import { pyodideInitialise } from './web-workers/init';

import App from './root';
import './index.scss';

ReactDOM.render(<App />, document.getElementById('root'));

pythonReady.subscribe(isReady => {
  if (isReady) {
    console.log("Python Ready")
  }
})

pyodideInitialise.subscribe(() => {
  pythonReady.next(true)
})

// If you want your app to work offline and load faster, you can change
// unregister() to register() below. Note this comes with some pitfalls.
// Learn more about service workers: https://bit.ly/CRA-PWA
serviceWorker.register();