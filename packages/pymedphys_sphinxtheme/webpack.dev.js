const path = require('path');
const merge = require('webpack-merge');
const common = require('./webpack.common.js');
const exec = require('child_process').exec;

module.exports = merge(common, {
    mode: 'development',
    plugins: [
        {
            apply: (compiler) => {
                compiler.hooks.environment.tap('StartServer', (compilation) => {
                    exec('rm -rf docs/_build', (err, stdout, stderr) => {
                        if (stdout) process.stdout.write(stdout);
                        if (stderr) process.stderr.write(stderr);
                    });
                });

                compiler.hooks.watchRun.tap('CleanWhenTriggered', (compilation) => {
                    exec('rm -rf docs/_build', (err, stdout, stderr) => {
                        if (stdout) process.stdout.write(stdout);
                        if (stderr) process.stderr.write(stderr);
                    });
                });

                compiler.hooks.afterEmit.tap('AfterEmitPlugin', (compilation) => {
                    exec('sphinx-build docs docs/_build/html', (err, stdout, stderr) => {
                        if (stdout) process.stdout.write(stdout);
                        if (stderr) process.stderr.write(stderr);
                    });
                });
            }
        }
    ],
    watch: true,
    devServer: {
        contentBase: path.join(__dirname, 'docs/_build/html'),
        compress: false,
        port: 7070
    }
});