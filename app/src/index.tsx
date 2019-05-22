import React from 'react';
import ReactDOM from 'react-dom';

import * as serviceWorker from './serviceWorker';

import { runPyodide } from './web-workers/init';

import App from './root';
import './index.scss';




ReactDOM.render(<App />, document.getElementById('root'));

runPyodide()



// If you want your app to work offline and load faster, you can change
// unregister() to register() below. Note this comes with some pitfalls.
// Learn more about service workers: https://bit.ly/CRA-PWA
serviceWorker.register();