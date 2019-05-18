import React from 'react';
import ReactDOM from 'react-dom';
import './index.css';
import App from './App';
import * as serviceWorker from './serviceWorker';


/*-----------------------------------------------------------------------------
| Copyright (c) 2014-2015, PhosphorJS Contributors
|
| Distributed under the terms of the BSD 3-Clause License.
|
| The full license is in the file LICENSE, distributed with this software.
|----------------------------------------------------------------------------*/

import {
  Menu, MenuBar, MenuItem
} from 'phosphor-menus';

import {
  Message
} from 'phosphor-messaging';

import {
  TabPanel
} from 'phosphor-tabs';

import {
  Widget
} from 'phosphor-widget';

import './index.css';


/**
 * Create the example menu bar.
 */
function createMenuBar(): MenuBar {
  let fileMenu = new Menu([
    new MenuItem({
      text: 'New File',
      shortcut: 'Ctrl+N'
    }),
    new MenuItem({
      text: 'Open File',
      shortcut: 'Ctrl+O'
    }),
    new MenuItem({
      text: 'Save File',
      shortcut: 'Ctrl+S'
    }),
    new MenuItem({
      text: 'Save As...',
      shortcut: 'Ctrl+Shift+S',
      disabled: true
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Close File',
      shortcut: 'Ctrl+W'
    }),
    new MenuItem({
      text: 'Close All'
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'More...',
      submenu: new Menu([
        new MenuItem({
          text: 'One'
        }),
        new MenuItem({
          text: 'Two'
        }),
        new MenuItem({
          text: 'Three'
        }),
        new MenuItem({
          text: 'Four'
        })
      ])
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Exit'
    })
  ]);

  let editMenu = new Menu([
    new MenuItem({
      text: '&Undo',
      icon: 'fa fa-undo',
      shortcut: 'Ctrl+Z'
    }),
    new MenuItem({
      text: '&Repeat',
      icon: 'fa fa-repeat',
      shortcut: 'Ctrl+Y',
      disabled: true
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: '&Copy',
      icon: 'fa fa-copy',
      shortcut: 'Ctrl+C'
    }),
    new MenuItem({
      text: 'Cu&t',
      icon: 'fa fa-cut',
      shortcut: 'Ctrl+X'
    }),
    new MenuItem({
      text: '&Paste',
      icon: 'fa fa-paste',
      shortcut: 'Ctrl+V'
    })
  ]);

  let findMenu = new Menu([
    new MenuItem({
      text: 'Find...',
      shortcut: 'Ctrl+F'
    }),
    new MenuItem({
      text: 'Find Next',
      shortcut: 'F3'
    }),
    new MenuItem({
      text: 'Find Previous',
      shortcut: 'Shift+F3'
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Replace...',
      shortcut: 'Ctrl+H'
    }),
    new MenuItem({
      text: 'Replace Next',
      shortcut: 'Ctrl+Shift+H'
    })
  ]);

  let helpMenu = new Menu([
    new MenuItem({
      text: 'Documentation'
    }),
    new MenuItem({
      text: 'About'
    })
  ]);

  return new MenuBar([
    new MenuItem({
      text: 'File',
      submenu: fileMenu
    }),
    new MenuItem({
      text: 'Edit',
      submenu: editMenu
    }),
    new MenuItem({
      text: 'Find',
      submenu: findMenu
    }),
    new MenuItem({
      text: 'View',
      type: MenuItem.Submenu
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Help',
      submenu: helpMenu
    })
  ]);
}


/**
 * Create the example context menu.
 */
function createContextMenu(): Menu {
  return new Menu([
    new MenuItem({
      text: '&Copy',
      icon: 'fa fa-copy',
      shortcut: 'Ctrl+C'
    }),
    new MenuItem({
      text: 'Cu&t',
      icon: 'fa fa-cut',
      shortcut: 'Ctrl+X'
    }),
    new MenuItem({
      text: '&Paste',
      icon: 'fa fa-paste',
      shortcut: 'Ctrl+V'
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: '&New Tab'
    }),
    new MenuItem({
      text: '&Close Tab'
    }),
    new MenuItem({
      type: MenuItem.Check,
      text: '&Save On Exit'
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Task Manager',
      disabled: true
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'More...',
      submenu: new Menu([
        new MenuItem({
          text: 'One'
        }),
        new MenuItem({
          text: 'Two'
        }),
        new MenuItem({
          text: 'Three'
        }),
        new MenuItem({
          text: 'Four'
        })
      ])
    }),
    new MenuItem({
      type: MenuItem.Separator
    }),
    new MenuItem({
      text: 'Close',
      icon: 'fa fa-close'
    })
  ]);
}


class TodoWidget extends Widget {

  static createNode(): HTMLElement {
    var node = document.createElement('div');
    var app = document.createElement('div');
    app.className = 'todoapp';
    app.id = 'output'
    node.appendChild(app);
    return node;
  }

  constructor() {
    super();
    this.addClass('TodoWidget');
  }

  protected onUpdateRequest(msg: Message): void {
    // var host = this.node.firstChild as Element;
    // ReactDOM.render(, host);
    ReactDOM.render(<App />, document.getElementById('output'));
  }
}



/**
 * The main application entry point.
 */
function main(): void {
  var contextArea = new TodoWidget();
  contextArea.addClass('ContextArea');
  // contextArea.node.innerHTML = (
  //   '<h2>Notice the menu bar at the top of the document.</h2>' +
  //   '<h2>Right click this panel for a context menu.</h2>' +
  //   '<h3>Clicked Item: <span id="log-span"></span></h3>'
  // );
  contextArea.title.text = 'React';

  var contextMenu = createContextMenu();
  contextArea.node.addEventListener('contextmenu', (event: MouseEvent) => {
    event.preventDefault();
    var x = event.clientX;
    var y = event.clientY;
    contextMenu.popup(x, y);
  });

  var menuBar = createMenuBar();

  var panel = new TabPanel();
  panel.id = 'main';
  panel.addChild(contextArea);

  menuBar.attach(document.body);
  panel.attach(document.body);

  contextArea.update();

  window.onresize = () => { panel.update() };
}


// If you want your app to work offline and load faster, you can change
// unregister() to register() below. Note this comes with some pitfalls.
// Learn more about service workers: https://bit.ly/CRA-PWA
serviceWorker.unregister();



window.onload = main;