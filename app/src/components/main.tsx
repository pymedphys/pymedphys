import React from 'react';

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

        <AppUserScripts />

      </div>
    );
  }
}
