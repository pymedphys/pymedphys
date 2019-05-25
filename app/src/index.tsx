import React from 'react';
import ReactDOM from 'react-dom';

import * as serviceWorker from './serviceWorker';

import App from './root';
import './index.scss';

import { startPyodide } from './pyodide';

ReactDOM.render(<App />, document.getElementById('root'));

startPyodide();

// If you want your app to work offline and load faster, you can change
// unregister() to register() below. Note this comes with some pitfalls.
// Learn more about service workers: https://bit.ly/CRA-PWA
serviceWorker.unregister();