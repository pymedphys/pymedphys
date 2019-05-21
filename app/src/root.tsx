import React from 'react';

import {
  Classes
} from '@blueprintjs/core';

import { AppMain } from './components/main';

interface IAppRootProps { }
interface IAppRootState extends Readonly<{}> { }

class AppRoot extends React.Component<IAppRootProps, IAppRootState> {
  render() {
    return (
      <div className="AppRoot">

        <AppMain />

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



