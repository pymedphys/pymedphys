import {
  OutputArea,
  OutputAreaModel
} from '@jupyterlab/outputarea';

import {
  RenderMimeRegistry,
  standardRendererFactories as initialFactories
} from '@jupyterlab/rendermime';

import { Kernel } from '@jupyterlab/services';

import { CommandRegistry } from '@phosphor/commands';

import { CommandPalette, SplitPanel, Widget } from '@phosphor/widgets';

import { ServiceManager } from '@jupyterlab/services';

import { editorServices } from '@jupyterlab/codemirror';

import { ConsolePanel } from '@jupyterlab/console';

const rendermime = new RenderMimeRegistry({ initialFactories });
const kernelPromise = Kernel.startNew()

let manager = new ServiceManager();

export function matplotlib(app: HTMLDivElement) {
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
  const model = new OutputAreaModel();
  const outputArea = new OutputArea({ model, rendermime });

  kernelPromise.then(kernel => {
    outputArea.future = kernel.requestExecute({ code });
    Widget.attach(outputArea, app)
  });

  return { model, code }
}

export function createConsole(app: HTMLDivElement) {
  manager.ready.then(() => {
    console(app, manager)
  })
}

function console(app: HTMLDivElement, manager: ServiceManager.IManager) {
  let commands = new CommandRegistry();

  // Setup the keydown listener for the document.
  document.addEventListener('keydown', event => {
    commands.processKeydownEvent(event);
  });

  let editorFactory = editorServices.factoryService.newInlineEditor;
  let contentFactory = new ConsolePanel.ContentFactory({ editorFactory });
  let consolePanel = new ConsolePanel({
    rendermime,
    manager,
    contentFactory,
    mimeTypeService: editorServices.mimeTypeService
  });

  let palette = new CommandPalette({ commands });

  let panel = new SplitPanel();
  panel.id = 'main';
  panel.orientation = 'horizontal';
  panel.spacing = 0;
  SplitPanel.setStretch(palette, 0);
  SplitPanel.setStretch(consolePanel, 1);
  panel.addWidget(palette);
  panel.addWidget(consolePanel);

  // Attach the panel to the DOM.
  Widget.attach(panel, app);

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
  palette.addItem({ command, category });

  command = 'console:execute';
  commands.addCommand(command, {
    label: 'Execute Prompt',
    execute: () => {
      consolePanel.console.execute();
    }
  });
  palette.addItem({ command, category });
  commands.addKeyBinding({ command, selector, keys: ['Enter'] });

  command = 'console:execute-forced';
  commands.addCommand(command, {
    label: 'Execute Cell (forced)',
    execute: () => {
      consolePanel.console.execute(true);
    }
  });
  palette.addItem({ command, category });
  commands.addKeyBinding({ command, selector, keys: ['Shift Enter'] });

  command = 'console:linebreak';
  commands.addCommand(command, {
    label: 'Insert Line Break',
    execute: () => {
      consolePanel.console.insertLinebreak();
    }
  });
  palette.addItem({ command, category });
  commands.addKeyBinding({ command, selector, keys: ['Ctrl Enter'] });
}