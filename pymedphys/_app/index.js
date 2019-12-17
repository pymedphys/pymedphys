// Code adapted from
// https://github.com/jupyterlab/jupyterlab/blob/1d787dbe2/examples/app/index.js

// Original code under the following license:
// ===================================================================
// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.
// See https://github.com/jupyterlab/jupyterlab/blob/1d787dbe2/LICENSE
// for more details.
// ===================================================================

// Modifications under the following license:
// ========================================================================
// Copyright (C) 2019 Simon Biggs

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
// ========================================================================

import { PageConfig } from '@jupyterlab/coreutils';
// eslint-disable-next-line
__webpack_public_path__ = PageConfig.getOption('fullStaticUrl') + '/';

// This must be after the public path is set.
// This cannot be extracted because the public path is dynamic.
require('./build/imports.css');

window.addEventListener('load', async function () {
  var JupyterLab = require('@jupyterlab/application').JupyterLab;

  var mods = [
    require('@jupyterlab/application-extension'),
    require('@jupyterlab/apputils-extension'),
    require('@jupyterlab/codemirror-extension'),
    require('@jupyterlab/completer-extension'),
    require('@jupyterlab/console-extension'),
    require('@jupyterlab/csvviewer-extension'),
    require('@jupyterlab/docmanager-extension'),
    require('@jupyterlab/fileeditor-extension'),
    require('@jupyterlab/filebrowser-extension'),
    require('@jupyterlab/help-extension'),
    require('@jupyterlab/imageviewer-extension'),
    require('@jupyterlab/inspector-extension'),
    require('@jupyterlab/launcher-extension'),
    require('@jupyterlab/mainmenu-extension'),
    require('@jupyterlab/markdownviewer-extension'),
    require('@jupyterlab/mathjax2-extension'),
    require('@jupyterlab/notebook-extension'),
    require('@jupyterlab/rendermime-extension'),
    require('@jupyterlab/running-extension'),
    require('@jupyterlab/settingeditor-extension'),
    require('@jupyterlab/shortcuts-extension'),
    require('@jupyterlab/statusbar-extension'),
    require('@jupyterlab/tabmanager-extension'),
    require('@jupyterlab/terminal-extension'),
    require('@jupyterlab/theme-dark-extension'),
    require('@jupyterlab/theme-light-extension'),
    require('@jupyterlab/tooltip-extension'),
    require('@jupyterlab/ui-components-extension')
  ];
  var lab = new JupyterLab();
  lab.registerPluginModules(mods);
  /* eslint-disable no-console */
  console.log('Starting app');
  await lab.start();
  console.log('App started, waiting for restore');
  await lab.restored;
  console.log('Example started!');
});
