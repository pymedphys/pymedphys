const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const exec = require('child_process').exec;

module.exports = {
    entry: './src/index.js',
    output: {
        filename: 'js/theme.js',
        path: path.resolve(__dirname, 'pymedphys_sphinxtheme/static')
    },
    module: {
        rules: [
            {
                test: require.resolve('./src/theme.js'),
                use: 'imports-loader?this=>window'
            },
            {
                test: /\.sass$/,
                use: [{
                    loader: MiniCssExtractPlugin.loader
                }, {
                    loader: "css-loader"
                }, {
                    loader: "sass-loader?indentedSyntax",
                    options: {
                        includePaths: [
                            'node_modules/bourbon/app/assets/stylesheets',
                            'node_modules/bourbon-neat/app/assets/stylesheets',
                            'node_modules/font-awesome/scss',
                            'node_modules/wyrm/sass'
                        ]
                    }
                }]
            },
            {
                test: /\.(woff(2)?|ttf|eot|svg)(\?v=\d+\.\d+\.\d+)?$/,
                use: [{
                    loader: 'file-loader',
                    options: {
                        name: '[name].[ext]',
                        outputPath: 'fonts/',
                        publicPath: '/_static/fonts',
                    }
                }]
            }
        ]
    },
    plugins: [
        new MiniCssExtractPlugin({
            // Options similar to the same options in webpackOptions.output
            // both options are optional
            filename: 'css/theme.css'
        }),
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
};