const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = {
    entry: './src/theme.js',
    output: {
        filename: 'js/theme.js',
        path: path.resolve(__dirname, 'pymedphys_sphinxtheme/static')
    },
    module: {
        rules: [{
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
        }]
    },
    plugins: [
        new MiniCssExtractPlugin({
            // Options similar to the same options in webpackOptions.output
            // both options are optional
            filename: 'css/theme.css'
        }),
    ]
};