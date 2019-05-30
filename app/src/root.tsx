import React from 'react';
import { BrowserRouter, Route, Switch } from "react-router-dom";

import { Classes } from '@blueprintjs/core';

import { AppMain } from './components/main';
import { AppPythonEngine } from './components/python-engine'

interface IAppRootProps { }
interface IAppRootState extends Readonly<{}> { }

class AppRoot extends React.Component<IAppRootProps, IAppRootState> {
  render() {
    return (
      <div className="AppRoot">

        <BrowserRouter>
          <Switch>
            <Route path="/python-engine/" exact component={AppPythonEngine} />
            <Route path="*" component={AppMain} />
          </Switch>
        </BrowserRouter>

        <div className={`${Classes.DRAWER_FOOTER} big-top-margin`}>
          <a className={'floatright'} href="https://www.netlify.com">
            <img
              alt="Build, deploy, and manage modern web projects"
              src="https://www.netlify.com/img/global/badges/netlify-light.svg">
            </img>
          </a>
        </div>

      </div>
    );
  }
}

export default AppRoot;



