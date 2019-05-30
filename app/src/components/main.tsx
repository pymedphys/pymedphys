import React from 'react';
import { BrowserRouter as Router, Route, Link } from "react-router-dom";


import {
  Tabs, Tab, H3, Icon
} from '@blueprintjs/core';


import { AppNavbar } from './navbar';
import { AppUserScripts } from './user-scripts';
import { placeholder } from '@babel/types';


interface IAppMainProps {

}

interface IAppMainState extends Readonly<{}> {

}

export class AppMain extends React.Component<IAppMainProps, IAppMainState> {


  constructor(props: IAppMainProps) {
    super(props)
    this.state = {
    }
  }

  render() {
    return (
      <div className="AppMain">
        <AppNavbar />

        {/* <Tabs
          animate={true}
          id="Tabs"
          vertical={true}
          renderActiveTabPanelOnly={true}
        >
          <Tab id="UserScripts" title={<span><Icon icon={"code"} /> User Scripts</span>} panel={<AppUserScripts />} />
          <Tab id="GammaAnalysis" title={<span><Icon icon={"grid"} /> Gamma Analysis</span>} panel={<Placeholder />} />
          <Tab id="PythonEngine" title={<span><Icon icon={"function"} /> Python Engine</span>} panel={<Placeholder />} />
        </Tabs> */}



        <Router>

          <Tabs
            animate={true}
            id="Tabs"
            vertical={true}
          >
            <Tab id="UserScripts" title={
              <Link to="/user-scripts/"><Icon icon={"code"} /> User Scripts</Link>
            } />
            <Tab id="GammaAnalysis" title={
              <Link to="/gamma-analysis/"><Icon icon={"grid"} /> Gamma Analysis</Link>
            } />
            <Tab id="PythonEngine" title={
              <Link to="/python-engine/"><Icon icon={"function"} /> Python Engine</Link>
            } />
          </Tabs>

          <div className="TabPadding">
            <Route path="/" exact component={Placeholder} />
            <Route path="/user-scripts/" exact component={AppUserScripts} />
            <Route path="/gamma-analysis/" exact component={Placeholder} />
            <Route path="/python-engine/" exact component={Placeholder} />
          </div>
        </Router>


      </div>
    );
  }
}

const Placeholder: React.SFC<{}> = () => (
  <div>
    <H3>Placeholder</H3>
  </div>
);