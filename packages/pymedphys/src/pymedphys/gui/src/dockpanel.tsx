/*-----------------------------------------------------------------------------
| Copyright (c) 2014-2017, PhosphorJS Contributors
|
| Distributed under the terms of the BSD 3-Clause License.
|
| The full license is in the file LICENSE, distributed with this software.
|----------------------------------------------------------------------------*/


import {
  CommandRegistry
} from '@phosphor/commands';

import {
  Message
} from '@phosphor/messaging';

import { ArrayExt, find, IIterator, iter, toArray } from '@phosphor/algorithm';

import {
  BoxPanel, ContextMenu, DockPanel, Menu, MenuBar, Widget, TabBar, StackedPanel,
  Title, SplitPanel, BoxLayout
} from '@phosphor/widgets';

import {
  createConsole
} from './jupyter';


export interface IRankItem {
  /**
   * The widget for the item.
   */
  widget: Widget;

  /**
   * The sort rank of the widget.
   */
  rank: number;
}


/**
 * A less-than comparison function for side bar rank items.
 */
export function itemCmp(first: IRankItem, second: IRankItem): number {
  return first.rank - second.rank;
}


class SideBarHandler {
  /**
   * Construct a new side bar handler.
   */
  constructor(side: string) {
    this._side = side;
    this._sideBar = new TabBar<Widget>({
      insertBehavior: 'none',
      removeBehavior: 'none',
      allowDeselect: true
    });
    this._stackedPanel = new StackedPanel();
    this._sideBar.hide();
    this._stackedPanel.hide();
    this._lastCurrent = null;
    this._sideBar.currentChanged.connect(
      this._onCurrentChanged,
      this
    );
    this._sideBar.tabActivateRequested.connect(
      this._onTabActivateRequested,
      this
    );
    this._stackedPanel.widgetRemoved.connect(
      this._onWidgetRemoved,
      this
    );
  }

  /**
   * Get the tab bar managed by the handler.
   */
  get sideBar(): TabBar<Widget> {
    return this._sideBar;
  }

  /**
   * Get the stacked panel managed by the handler
   */
  get stackedPanel(): StackedPanel {
    return this._stackedPanel;
  }

  /**
   * Expand the sidebar.
   *
   * #### Notes
   * This will open the most recently used tab, or the first tab
   * if there is no most recently used.
   */
  expand(): void {
    const previous =
      this._lastCurrent || (this._items.length > 0 && this._items[0].widget);
    if (previous) {
      this.activate(previous.id);
    }
  }

  /**
   * Activate a widget residing in the side bar by ID.
   *
   * @param id - The widget's unique ID.
   */
  activate(id: string): void {
    let widget = this._findWidgetByID(id);
    if (widget) {
      this._sideBar.currentTitle = widget.title;
      widget.activate();
    }
  }

  /**
   * Test whether the sidebar has the given widget by id.
   */
  has(id: string): boolean {
    return this._findWidgetByID(id) !== null;
  }

  /**
   * Collapse the sidebar so no items are expanded.
   */
  collapse(): void {
    this._sideBar.currentTitle = null;
  }

  /**
   * Add a widget and its title to the stacked panel and side bar.
   *
   * If the widget is already added, it will be moved.
   */
  addWidget(widget: Widget, rank: number): void {
    widget.parent = null;
    widget.hide();
    let item = { widget, rank };
    let index = this._findInsertIndex(item);
    ArrayExt.insert(this._items, index, item);
    this._stackedPanel.insertWidget(index, widget);
    const title = this._sideBar.insertTab(index, widget.title);
    // Store the parent id in the title dataset
    // in order to dispatch click events to the right widget.
    title.dataset = { id: widget.id };
    this._refreshVisibility();
  }


  /**
   * Find the insertion index for a rank item.
   */
  private _findInsertIndex(item: IRankItem): number {
    return ArrayExt.upperBound(this._items, item, itemCmp);
  }

  /**
   * Find the index of the item with the given widget, or `-1`.
   */
  private _findWidgetIndex(widget: Widget): number {
    return ArrayExt.findFirstIndex(this._items, i => i.widget === widget);
  }

  /**
   * Find the widget which owns the given title, or `null`.
   */
  private _findWidgetByTitle(title: Title<Widget>): Widget | null {
    let item = find(this._items, value => value.widget.title === title);
    return item ? item.widget : null;
  }

  /**
   * Find the widget with the given id, or `null`.
   */
  private _findWidgetByID(id: string): Widget | null {
    let item = find(this._items, value => value.widget.id === id);
    return item ? item.widget : null;
  }

  /**
   * Refresh the visibility of the side bar and stacked panel.
   */
  private _refreshVisibility(): void {
    this._sideBar.setHidden(this._sideBar.titles.length === 0);
    this._stackedPanel.setHidden(this._sideBar.currentTitle === null);
  }

  /**
   * Handle the `currentChanged` signal from the sidebar.
   */
  private _onCurrentChanged(
    sender: TabBar<Widget>,
    args: TabBar.ICurrentChangedArgs<Widget>
  ): void {
    const oldWidget = args.previousTitle
      ? this._findWidgetByTitle(args.previousTitle)
      : null;
    const newWidget = args.currentTitle
      ? this._findWidgetByTitle(args.currentTitle)
      : null;
    if (oldWidget) {
      oldWidget.hide();
    }
    if (newWidget) {
      newWidget.show();
    }
    this._lastCurrent = newWidget || oldWidget;
    if (newWidget) {
      const id = newWidget.id;
      document.body.setAttribute(`data-${this._side}-sidebar-widget`, id);
    } else {
      document.body.removeAttribute(`data-${this._side}-sidebar-widget`);
    }
    this._refreshVisibility();
  }

  /**
   * Handle a `tabActivateRequest` signal from the sidebar.
   */
  private _onTabActivateRequested(
    sender: TabBar<Widget>,
    args: TabBar.ITabActivateRequestedArgs<Widget>
  ): void {
    args.title.owner.activate();
  }

  /*
   * Handle the `widgetRemoved` signal from the stacked panel.
   */
  private _onWidgetRemoved(sender: StackedPanel, widget: Widget): void {
    if (widget === this._lastCurrent) {
      this._lastCurrent = null;
    }
    ArrayExt.removeAt(this._items, this._findWidgetIndex(widget));
    this._sideBar.removeTab(widget.title);
    this._refreshVisibility();
  }

  private _items = new Array<IRankItem>();
  private _side: string;
  private _sideBar: TabBar<Widget>;
  private _stackedPanel: StackedPanel;
  private _lastCurrent: Widget | null;
}


const commands = new CommandRegistry();

function createMenu(): Menu {
  let sub1 = new Menu({ commands });
  sub1.title.label = 'More...';
  sub1.title.mnemonic = 0;
  sub1.addItem({ command: 'example:one' });
  sub1.addItem({ command: 'example:two' });
  sub1.addItem({ command: 'example:three' });
  sub1.addItem({ command: 'example:four' });

  let sub2 = new Menu({ commands });
  sub2.title.label = 'More...';
  sub2.title.mnemonic = 0;
  sub2.addItem({ command: 'example:one' });
  sub2.addItem({ command: 'example:two' });
  sub2.addItem({ command: 'example:three' });
  sub2.addItem({ command: 'example:four' });
  sub2.addItem({ type: 'submenu', submenu: sub1 });

  let root = new Menu({ commands });
  root.addItem({ command: 'example:copy' });
  root.addItem({ command: 'example:cut' });
  root.addItem({ command: 'example:paste' });
  root.addItem({ type: 'separator' });
  root.addItem({ command: 'example:new-tab' });
  root.addItem({ command: 'example:close-tab' });
  root.addItem({ command: 'example:save-on-exit' });
  root.addItem({ type: 'separator' });
  root.addItem({ command: 'example:open-task-manager' });
  root.addItem({ type: 'separator' });
  root.addItem({ type: 'submenu', submenu: sub2 });
  root.addItem({ type: 'separator' });
  root.addItem({ command: 'example:close' });

  return root;
}

class ContentWidget extends Widget {

  static createNode(): HTMLElement {
    let node = document.createElement('div');
    let content = document.createElement('div');
    let input = document.createElement('input');
    input.placeholder = 'Placeholder...';
    content.appendChild(input);
    node.appendChild(content);
    return node;
  }

  constructor(name: string) {
    super({ node: ContentWidget.createNode() });
    this.setFlag(Widget.Flag.DisallowLayout);
    this.addClass('content');
    this.addClass(name.toLowerCase());
    this.title.label = name;
    this.title.closable = false;
    this.title.caption = `Long description for: ${name}`;
  }

  get inputNode(): HTMLInputElement {
    return this.node.getElementsByTagName('input')[0] as HTMLInputElement;
  }

  protected onActivateRequest(msg: Message): void {
    if (this.isAttached) {
      this.inputNode.focus();
    }
  }
}



export function dockpanel(root: HTMLDivElement): void {
  commands.addCommand('example:cut', {
    label: 'Cut',
    mnemonic: 1,
    iconClass: 'fa fa-cut',
    execute: () => {
      console.log('Cut');
    }
  });

  commands.addCommand('example:copy', {
    label: 'Copy File',
    mnemonic: 0,
    iconClass: 'fa fa-copy',
    execute: () => {
      console.log('Copy');
    }
  });

  commands.addCommand('example:paste', {
    label: 'Paste',
    mnemonic: 0,
    iconClass: 'fa fa-paste',
    execute: () => {
      console.log('Paste');
    }
  });

  commands.addCommand('example:new-tab', {
    label: 'New Tab',
    mnemonic: 0,
    caption: 'Open a new tab',
    execute: () => {
      console.log('New Tab');
    }
  });

  commands.addCommand('example:close-tab', {
    label: 'Close Tab',
    mnemonic: 2,
    caption: 'Close the current tab',
    execute: () => {
      console.log('Close Tab');
    }
  });

  commands.addCommand('example:save-on-exit', {
    label: 'Save on Exit',
    mnemonic: 0,
    caption: 'Toggle the save on exit flag',
    execute: () => {
      console.log('Save on Exit');
    }
  });

  commands.addCommand('example:open-task-manager', {
    label: 'Task Manager',
    mnemonic: 5,
    isEnabled: () => false,
    execute: () => { }
  });

  commands.addCommand('example:close', {
    label: 'Close',
    mnemonic: 0,
    iconClass: 'fa fa-close',
    execute: () => {
      console.log('Close');
    }
  });

  commands.addCommand('example:one', {
    label: 'One',
    execute: () => {
      console.log('One');
    }
  });

  commands.addCommand('example:two', {
    label: 'Two',
    execute: () => {
      console.log('Two');
    }
  });

  commands.addCommand('example:three', {
    label: 'Three',
    execute: () => {
      console.log('Three');
    }
  });

  commands.addCommand('example:four', {
    label: 'Four',
    execute: () => {
      console.log('Four');
    }
  });

  commands.addCommand('example:black', {
    label: 'Black',
    execute: () => {
      console.log('Black');
    }
  });

  commands.addCommand('example:clear-cell', {
    label: 'Clear Cell',
    execute: () => {
      console.log('Clear Cell');
    }
  });

  commands.addCommand('example:cut-cells', {
    label: 'Cut Cell(s)',
    execute: () => {
      console.log('Cut Cell(s)');
    }
  });

  commands.addCommand('example:run-cell', {
    label: 'Run Cell',
    execute: () => {
      console.log('Run Cell');
    }
  });

  commands.addCommand('example:cell-test', {
    label: 'Cell Test',
    execute: () => {
      console.log('Cell Test');
    }
  });

  commands.addCommand('notebook:new', {
    label: 'New Notebook',
    execute: () => {
      console.log('New Notebook');
    }
  });

  commands.addKeyBinding({
    keys: ['Accel X'],
    selector: 'body',
    command: 'example:cut'
  });

  commands.addKeyBinding({
    keys: ['Accel C'],
    selector: 'body',
    command: 'example:copy'
  });

  commands.addKeyBinding({
    keys: ['Accel V'],
    selector: 'body',
    command: 'example:paste'
  });

  commands.addKeyBinding({
    keys: ['Accel J', 'Accel J'],
    selector: 'body',
    command: 'example:new-tab'
  });

  commands.addKeyBinding({
    keys: ['Accel M'],
    selector: 'body',
    command: 'example:open-task-manager'
  });

  let menu1 = createMenu();
  menu1.title.label = 'File';
  menu1.title.mnemonic = 0;

  let menu2 = createMenu();
  menu2.title.label = 'Edit';
  menu2.title.mnemonic = 0;

  let menu3 = createMenu();
  menu3.title.label = 'View';
  menu3.title.mnemonic = 0;

  let bar = new MenuBar();
  bar.addMenu(menu1);
  bar.addMenu(menu2);
  bar.addMenu(menu3);
  bar.id = 'menuBar';

  let contextMenu = new ContextMenu({ commands });

  document.addEventListener('contextmenu', (event: MouseEvent) => {
    if (contextMenu.open(event)) {
      event.preventDefault();
    }
  });

  contextMenu.addItem({ command: 'example:cut', selector: '.content' });
  contextMenu.addItem({ command: 'example:copy', selector: '.content' });
  contextMenu.addItem({ command: 'example:paste', selector: '.content' });

  contextMenu.addItem({ command: 'example:one', selector: '.p-CommandPalette' });
  contextMenu.addItem({ command: 'example:two', selector: '.p-CommandPalette' });
  contextMenu.addItem({ command: 'example:three', selector: '.p-CommandPalette' });
  contextMenu.addItem({ command: 'example:four', selector: '.p-CommandPalette' });
  contextMenu.addItem({ command: 'example:black', selector: '.p-CommandPalette' });

  contextMenu.addItem({ command: 'notebook:new', selector: '.p-CommandPalette-input' });
  contextMenu.addItem({ command: 'example:save-on-exit', selector: '.p-CommandPalette-input' });
  contextMenu.addItem({ command: 'example:open-task-manager', selector: '.p-CommandPalette-input' });
  contextMenu.addItem({ type: 'separator', selector: '.p-CommandPalette-input' });

  document.addEventListener('keydown', (event: KeyboardEvent) => {
    commands.processKeydownEvent(event);
  });

  let r1 = new ContentWidget('Console');
  r1.id = 'console';
  let b1 = new ContentWidget('Output');
  b1.id = 'output';
  let g1 = new ContentWidget('Table');
  g1.id = 'table';

  let dock = new DockPanel();
  dock.addWidget(b1);

  dock.addWidget(g1, { mode: 'split-right', ref: b1 });


  createConsole().then(consolePanel => {
    consolePanel.addClass('console')
    consolePanel.title.label = 'Console';
    consolePanel.title.closable = false;
    dock.addWidget(consolePanel, { mode: 'tab-after', ref: g1 });
    // rightHandler.addWidget(consolePanel, 1)
  })


  dock.id = 'dock';

  let savedLayouts: DockPanel.ILayoutConfig[] = [];

  commands.addCommand('save-dock-layout', {
    label: 'Save Layout',
    caption: 'Save the current dock layout',
    execute: () => {
      savedLayouts.push(dock.saveLayout());
    }
  });

  commands.addCommand('restore-dock-layout', {
    label: args => {
      return `Restore Layout ${args.index as number}`;
    },
    execute: args => {
      dock.restoreLayout(savedLayouts[args.index as number]);
    }
  });

  let hsplitPanel = new SplitPanel({ orientation: 'horizontal', spacing: 0 });
  let hboxPanel = new BoxPanel({ direction: 'left-to-right', spacing: 0 });

  let rightHandler = new SideBarHandler('right');
  rightHandler.sideBar.addClass('jp-SideBar');
  rightHandler.sideBar.addClass('jp-mod-right');
  rightHandler.stackedPanel.id = 'jp-right-stack';

  let test = new Widget();
  rightHandler.addWidget(test, 0)

  let test2 = new Widget();
  rightHandler.addWidget(test2, 2)

  SplitPanel.setStretch(dock, 1);
  SplitPanel.setStretch(rightHandler.stackedPanel, 0)

  BoxPanel.setStretch(dock, 1);
  BoxPanel.setStretch(rightHandler.sideBar, 0);

  hsplitPanel.addWidget(dock);
  hsplitPanel.addWidget(rightHandler.stackedPanel);

  hboxPanel.addWidget(dock);
  hboxPanel.addWidget(rightHandler.sideBar);

  hsplitPanel.setRelativeSizes([2.5, 1]);

  let rootPanel = new BoxPanel({ direction: 'top-to-bottom', spacing: 0 });

  // rootPanel.addWidget(bar)

  let main = new BoxPanel({ direction: 'left-to-right', spacing: 0 });
  main.addClass('full-flex');
  main.addWidget(hboxPanel);


  rootPanel.addWidget(main)

  rootPanel.addClass('full-flex')
  window.onresize = () => { rootPanel.update(); };

  Widget.attach(bar, document.getElementById('root') as HTMLDivElement);
  Widget.attach(rootPanel, document.getElementById('root') as HTMLDivElement);
}