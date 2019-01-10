// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import React, { Component } from 'react';
// import ReactDOM from 'react-dom';

import { Button } from "@blueprintjs/core";

import {
  OutputArea,
  OutputAreaModel
} from '@jupyterlab/outputarea';

import { ClientSession, IClientSession } from '@jupyterlab/apputils';


import {
  RenderMimeRegistry,
  standardRendererFactories as initialFactories
} from '@jupyterlab/rendermime';

import { Kernel } from '@jupyterlab/services';

import { DocumentRegistry, Context } from '@jupyterlab/docregistry'

import { DocumentManager } from '@jupyterlab/docmanager';

import { CommandRegistry } from '@phosphor/commands';

import { DockPanel, Menu, CommandPalette, SplitPanel, Widget, Panel } from '@phosphor/widgets';

import { ServiceManager } from '@jupyterlab/services';

import { editorServices } from '@jupyterlab/codemirror';

import { ConsolePanel, CodeConsole } from '@jupyterlab/console';

import { BokehJSLoad, BokehJSExec, BOKEHJS_LOAD_MIME_TYPE, BOKEHJS_EXEC_MIME_TYPE } from 'jupyterlab_bokeh/lib/renderer';
import { ContextManager } from 'jupyterlab_bokeh/lib/manager';
// import { NBWidgetExtension } from 'jupyterlab_bokeh/lib/plugin';



// let dock = new DockPanel();

// let widgets: Widget[] = [];
// let activeWidget: Widget;

// let opener = {
//   open: (widget: Widget) => {
//     if (widgets.indexOf(widget) === -1) {
//       dock.addWidget(widget, { mode: 'tab-after' });
//       widgets.push(widget);
//     }
//     dock.activateWidget(widget);
//     activeWidget = widget;
//     widget.disposed.connect((w: Widget) => {
//       let index = widgets.indexOf(w);
//       widgets.splice(index, 1);
//     });
//   }
// };

let serviceManager = new ServiceManager();
// let docRegistry = new DocumentRegistry();
// let docManager = new DocumentManager({
//   registry: docRegistry,
//   manager: serviceManager,
//   opener
// });

// let context = new Context({
//   manager: serviceManager
// })

// let widget = new Widget()

// docManager

// docRegistry.addWidgetExtension('Notebook', new NBWidgetExtension())
// docRegistry

let context = {} as DocumentRegistry.IContext<DocumentRegistry.IModel>

let contextManager = new ContextManager(context);

const rendermime = new RenderMimeRegistry({ initialFactories });
rendermime.addFactory({
  safe: true,  // false
  mimeTypes: [BOKEHJS_LOAD_MIME_TYPE],
  createRenderer: (options) => new BokehJSLoad(options)
}, 0);

rendermime.addFactory({
  safe: true,  // false
  mimeTypes: [BOKEHJS_EXEC_MIME_TYPE],
  createRenderer: (options) => new BokehJSExec(options, contextManager)
}, -1);

const kernelPromise = Kernel.startNew()



export class CodeButtons extends Component {

  outputDiv: React.RefObject<HTMLDivElement>

  constructor(props: any) {
    super(props);
    this.outputDiv = React.createRef<HTMLDivElement>();
    this.runCode = this.runCode.bind(this);
    this.matplotlib = this.matplotlib.bind(this);
    this.bokeh = this.bokeh.bind(this);
  }

  // componentDidMount() {
  //   this.node = ReactDOM.findDOMNode(this) as HTMLElement
  // }

  matplotlib() {
    const code = [
      'import numpy as np',
      'import matplotlib.pyplot as plt',
      '%matplotlib inline',
      'x = np.linspace(-10,10)',
      'y = x**2',
      'print(x)',
      'print(y)',
      'plt.plot(x, y)'
    ].join('\n');
    this.runCode(code)
  }

  bokeh() {
    const code = [
      'import numpy as np',
      'from bokeh.plotting import figure, show, output_notebook',
      'output_notebook()',
      'N = 500',
      'x = np.linspace(0, 10, N)',
      'y = np.linspace(0, 10, N)',
      'xx, yy = np.meshgrid(x, y)',
      'd = np.sin(xx)*np.cos(yy)',
      'p = figure(x_range=(0, 10), y_range=(0, 10), tooltips=[("x", "$x"), ("y", "$y"), ("value", "@image")])',
      'p.image(image=[d], x=0, y=0, dw=10, dh=10, palette="Spectral11")',
      'show(p)'
    ].join('\n');
    this.runCode(code)
  }

  runCode(code: string) {
    const model = new OutputAreaModel();
    const outputArea = new OutputArea({ model, rendermime });

    kernelPromise.then(kernel => {
      let node = this.outputDiv.current as HTMLDivElement

      outputArea.future = kernel.requestExecute({ code });
      Widget.attach(outputArea, node)
    });
  }


  render() {
    return (
      <div>
        <Button icon="refresh" intent="primary" text="Matplotlib" onClick={this.matplotlib} />
        <Button icon="refresh" intent="primary" text="Bokeh" onClick={this.bokeh} />
        <div ref={this.outputDiv}></div>
      </div>
    )
  }
}


// export function matplotlib(app: HTMLDivElement) {
//   const code = [
//     'import numpy as np',
//     'import matplotlib.pyplot as plt',
//     '%matplotlib inline',
//     'x = np.linspace(-10,10)',
//     'y = x**2',
//     'print(x)',
//     'print(y)',
//     'plt.plot(x, y)'
//   ].join('\n');
//   const model = new OutputAreaModel();
//   const outputArea = new OutputArea({ model, rendermime });

//   kernelPromise.then(kernel => {
//     outputArea.future = kernel.requestExecute({ code });
//     Widget.attach(outputArea, app)
//   });

//   return { model, code }
// }









export function createConsole(): Promise<SplitPanel> {
  return serviceManager.ready.then(() => {
    return buildConsole(serviceManager)
  })
}

function buildConsole(manager: ServiceManager.IManager) {
  let commands = new CommandRegistry();

  // Setup the keydown listener for the document.
  document.addEventListener('keydown', event => {
    commands.processKeydownEvent(event);
  });

  let editorFactory = editorServices.factoryService.newInlineEditor;
  let contentFactory = new ConsolePanel.ContentFactory({ editorFactory });
  // let consoleWidget = new CodeConsole({
  //   contentFactory,
  //   rendermime,
  //   mimeTypeService: editorServices.mimeTypeService,
  //   session:
  // })
  let consolePanel = new ConsolePanel({
    rendermime,
    manager,
    contentFactory,
    mimeTypeService: editorServices.mimeTypeService
  });

  let panel = new SplitPanel();
  panel.id = 'console-panel';
  panel.orientation = 'horizontal';
  panel.spacing = 0;
  SplitPanel.setStretch(consolePanel, 1);
  panel.addWidget(consolePanel);

  // Attach the panel to the DOM.
  // Widget.attach(panel, app);

  // Handle resize events.
  window.addEventListener('resize', () => {
    panel.update();
  });

  let selector = '.jp-ConsolePanel';
  let category = 'Console';
  let command: string;

  // Add the commands.
  command = 'console:clear';
  commands.addCommand(command, {
    label: 'Clear',
    execute: () => {
      consolePanel.console.clear();
    }
  });

  command = 'console:execute';
  commands.addCommand(command, {
    label: 'Execute Prompt',
    execute: () => {
      consolePanel.console.execute();
    }
  });
  commands.addKeyBinding({ command, selector, keys: ['Enter'] });

  command = 'console:execute-forced';
  commands.addCommand(command, {
    label: 'Execute Cell (forced)',
    execute: () => {
      consolePanel.console.execute(true);
    }
  });
  commands.addKeyBinding({ command, selector, keys: ['Shift Enter'] });

  command = 'console:linebreak';
  commands.addCommand(command, {
    label: 'Insert Line Break',
    execute: () => {
      consolePanel.console.insertLinebreak();
    }
  });
  commands.addKeyBinding({ command, selector, keys: ['Ctrl Enter'] });

  return panel
}