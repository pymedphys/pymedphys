const childProcess = require("child_process");
const readline = require("readline");
const electron = require("electron");
const webpack = require("webpack");
const config = require("./webpack.app.config");

const compiler = webpack(config({ development: true }));
let electronStarted = false;

const watching = compiler.watch({}, (err, stats) => {
  if (err != null) {
    console.log(err);
  } else if (!electronStarted) {
    electronStarted = true;
    childProcess
      .spawn(electron, ["."], { stdio: "inherit" })
      .on("close", () => {
        watching.close();
      });
  }

  if (stats != null) {
    console.log(stats.toString({ colors: true }));
  }
});
