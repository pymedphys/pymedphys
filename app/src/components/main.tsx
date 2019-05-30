import React from 'react';
import { BrowserRouter, Route, Link, Redirect } from "react-router-dom";


import {
  Tabs, Tab, H3, Icon, AnchorButton
} from '@blueprintjs/core';

import { IconName } from "@blueprintjs/icons";

import { startPyodide, hookInMain } from '../observables/webworker-messaging/main';

import { AppNavbar } from './navbar';
import { AppUserScripts } from './user-scripts';
import { pythonReady } from '../observables/python';


interface IAppMainProps {

}

interface IAppMainState extends Readonly<{}> {
  path: string;
  pythonReady: boolean;
}


interface ITab {
  path: string;
  icon: IconName;
  label: string;
  newTab?: boolean;
}


const tabs: ITab[] = [
  {
    path: "/user-scripts/",
    icon: "code",
    label: "User Scripts"
  },
  {
    path: "/gamma-analysis/",
    icon: "grid",
    label: "Gamma Analysis"
  }
]

export class AppMain extends React.Component<IAppMainProps, IAppMainState> {


  constructor(props: IAppMainProps) {
    super(props)
    this.state = {
      path: window.location.pathname,
      pythonReady: false
    }
  }

  componentDidMount() {
    pythonReady.subscribe(ready => {
      this.setState({ pythonReady: ready })
    })

    hookInMain()
    startPyodide() // Do this only when the tab is ready, have a I'm here message be broadcast
    // at that point a "you're not needed" can also be sent. Receiving a "you're not needed"
    // will close that worker down.

  }

  render() {
    let display;

    if (this.state.pythonReady) {
      display = <div>
        <BrowserRouter>

          <Tabs
            animate={true}
            id="Tabs"
            vertical={true}
            selectedTabId={this.state.path}
          >
            {tabs.map(tab => {
              return <Tab id={tab.path} key={tab.path} title={
                <Link
                  to={tab.path}
                  onClick={() => this.setState({ path: tab.path })}
                ><Icon icon={tab.icon} /> {tab.label}</Link>
              } />
            })}

          </Tabs>

          <div className="TabPadding">
            <Route path="/" exact component={RedirectToUserScripts} />
            <Route path="/user-scripts/" exact component={AppUserScripts} />
            <Route path="/gamma-analysis/" exact component={Placeholder} />
          </div>
        </BrowserRouter>
      </div>
    } else {
      display = <AnchorButton
        icon="function" text="Python Engine"
        href="/python-engine/" onClick={startPyodide} target="_blank" />
    }

    return (
      <div className="AppMain">
        <AppNavbar />
        {display}
      </div>
    );
  }
}

const Placeholder: React.SFC<{}> = () => (
  <div>
    <H3>Placeholder</H3>
  </div>
);


const RedirectToUserScripts: React.SFC<{}> = () => (
  <Redirect to="/user-scripts/" />
);