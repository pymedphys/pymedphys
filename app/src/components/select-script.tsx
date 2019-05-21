import React from 'react';

import { Button, MenuItem } from "@blueprintjs/core";
import { Select, ItemPredicate, ItemRenderer } from '@blueprintjs/select';

import { IUserScript, USER_SCRIPTS } from '../python/user-scripts/options';

import { pythonCode } from '../observables/python';

/*
 * Copyright 2017 Palantir Technologies, Inc. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


// Select options code copied and modified from:
// https://github.com/palantir/blueprint/blob/06a186c90758bbdca604ed6d7bf639c3d05b1fa0/packages/docs-app/src/examples/select-examples/films.tsx


const UserScriptSelect = Select.ofType<IUserScript>();

const filterScripts: ItemPredicate<IUserScript> = (query, script, _index, exactMatch) => {
  const normalisedName = script.name.toLowerCase();
  const normalisedQuery = query.toLowerCase();

  if (exactMatch) {
    return normalisedName === normalisedQuery;
  } else {
    return `${script.name}. ${normalisedName} ${script.description}`.indexOf(normalisedQuery) >= 0;
  }
};


export const renderScripts: ItemRenderer<IUserScript> = (script, { handleClick, modifiers, query }) => {
  if (!modifiers.matchesPredicate) {
    return null;
  }
  const text = `${script.name}`;
  return (
    <MenuItem
      active={modifiers.active}
      disabled={modifiers.disabled}
      label={script.description}
      key={script.name}
      onClick={handleClick}
      text={highlightText(text, query)}
    />
  );
};

function escapeRegExpChars(text: string) {
  // eslint-disable-next-line
  return text.replace(/([.*+?^=!:${}()|\[\]\/\\])/g, "\\$1");
}

function highlightText(text: string, query: string) {
  let lastIndex = 0;
  const words = query
    .split(/\s+/)
    .filter(word => word.length > 0)
    .map(escapeRegExpChars);
  if (words.length === 0) {
    return [text];
  }
  const regexp = new RegExp(words.join("|"), "gi");
  const tokens: React.ReactNode[] = [];
  while (true) {
    const match = regexp.exec(text);
    if (!match) {
      break;
    }
    const length = match[0].length;
    const before = text.slice(lastIndex, regexp.lastIndex - length);
    if (before.length > 0) {
      tokens.push(before);
    }
    lastIndex = regexp.lastIndex;
    tokens.push(<strong key={lastIndex}>{match[0]}</strong>);
  }
  const rest = text.slice(lastIndex);
  if (rest.length > 0) {
    tokens.push(rest);
  }
  return tokens;
}

export function deleteScriptFromArray(scripts: IUserScript[], filmToDelete: IUserScript) {
  return scripts.filter(film => film !== filmToDelete);
}

export function arrayContainsScript(scripts: IUserScript[], filmToFind: IUserScript): boolean {
  return scripts.some((film: IUserScript) => film.name === filmToFind.name);
}

export function maybeDeleteCreatedFilmFromArrays(
  items: IUserScript[],
  createdItems: IUserScript[],
  script: IUserScript,
): { createdItems: IUserScript[]; items: IUserScript[] } {
  const wasItemCreatedByUser = arrayContainsScript(createdItems, script);

  return {
    createdItems: wasItemCreatedByUser ? deleteScriptFromArray(createdItems, script) : createdItems,
    items: wasItemCreatedByUser ? deleteScriptFromArray(items, script) : items,
  };
}

export function addScriptToArray(scripts: IUserScript[], scriptToAdd: IUserScript) {
  return [...scripts, scriptToAdd];
}

export function maybeAddCreatedScriptToArrays(
  items: IUserScript[],
  createdItems: IUserScript[],
  script: IUserScript,
): { createdItems: IUserScript[]; items: IUserScript[] } {
  const isNewlyCreatedItem = !arrayContainsScript(items, script);
  return {
    createdItems: isNewlyCreatedItem ? addScriptToArray(createdItems, script) : createdItems,
    items: isNewlyCreatedItem ? addScriptToArray(items, script) : items,
  };
}

interface IAppSelectScriptProps {

}

interface IAppSelectScript {
  createdItems: IUserScript[]
  script: IUserScript
  items: IUserScript[]
}


export class AppSelectScript extends React.Component<IAppSelectScriptProps, IAppSelectScript>{
  public state = {
    items: USER_SCRIPTS,
    createdItems: [],
    script: USER_SCRIPTS[0]
  }

  componentDidMount() {
    pythonCode.next(this.state.script.code)
  }

  private handleValueChange = (script: IUserScript) => {
    const { createdItems, items } = maybeDeleteCreatedFilmFromArrays(
      this.state.items,
      this.state.createdItems,
      this.state.script,
    );
    const { createdItems: nextCreatedItems, items: nextItems } = maybeAddCreatedScriptToArrays(
      items,
      createdItems,
      script,
    );
    pythonCode.next(script.code)
    this.setState({ createdItems: nextCreatedItems, script: script, items: nextItems });
  };

  render() {
    return (
      <UserScriptSelect
        itemPredicate={filterScripts}
        itemRenderer={renderScripts}
        items={this.state.items}
        onItemSelect={this.handleValueChange}
      >
        <Button
          icon="code"
          rightIcon="caret-down"
          intent="primary"
          text={this.state.script ? this.state.script.name : "(No selection)"}
        />
      </UserScriptSelect>
    )
  }
}