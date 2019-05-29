import React from 'react';

import {
  Tabs, Tab, H3, Icon
} from '@blueprintjs/core';


import { AppNavbar } from './navbar';
import { AppUserScripts } from './user-scripts';


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

        <Tabs
          animate={true}
          id="Tabs"
          vertical={true}
          renderActiveTabPanelOnly={true}
        >
          <Tab id="UserScripts" title={<span><Icon icon={"code"} /> User Scripts</span>} panel={<AppUserScripts />} />
          <Tab id="GammaAnalysis" title={<span><Icon icon={"grid"} /> Gamma Analysis</span>} panel={<Placeholder />} />
          <Tab id="PythonEngine" title={<span><Icon icon={"function"} /> Python Engine</span>} panel={<Placeholder />} />
        </Tabs>


      </div>
    );
  }
}

const Placeholder: React.SFC<{}> = () => (
  <div>
    <H3>Placeholder</H3>
  </div>
);