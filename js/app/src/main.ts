// Copyright (C) 2022 Simon Biggs

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


import path from "path";
import url from "url";
import { app, Menu, shell } from "electron";

import { spawn, ChildProcess } from "child_process";

import window from "./window";

// @ts-ignore
import env from "env";


let appStreamlitServer: ChildProcess;

// TODO: Make it so that the port is dynamically loaded from the streamlit start printout
// Potentially could have an option to suppress the streamlit printout and provide a json encoded port.
const pymedphysAppUrl = url.format({
  pathname: `localhost:8501`,
  protocol: "http:",
  slashes: true,
});

if (env.name === "development") {
  console.log("Development")
  appStreamlitServer = spawn("poetry", ["run", "pymedphys", "gui"]);
} else {
  appStreamlitServer = spawn("pymedphys",  ["gui"], {
    cwd: path.join(process.resourcesPath, "python"),
  });
}

appStreamlitServer.stderr.on("data", (data) => {
  console.log(`${data}`);
});

appStreamlitServer.stdout.on("data", (data) => {
  console.log(`${data}`);
});


app.on("web-contents-created", (event, contents) => {
  contents.on("will-navigate", (event, navigationUrl) => {
    event.preventDefault();

    const parsedUrl = new url.URL(navigationUrl);
    if (["https:", "http:", "mailto:"].includes(parsedUrl.protocol)) {
      shell.openExternal(navigationUrl);
    }
  });
});

app.on("ready", () => {
  // const menu = Menu.buildFromTemplate([devMenu]);

  Menu.setApplicationMenu(null);

  const mainWindow = window("main", {
    width: 500,
    height: 809,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });

  mainWindow.loadURL(pymedphysAppUrl);
});

app.on('before-quit', function() {
  appStreamlitServer.kill();
});

app.on("window-all-closed", () => {
  app.quit();
});
