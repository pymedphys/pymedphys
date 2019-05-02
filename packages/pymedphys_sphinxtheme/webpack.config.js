const path = require('path');

module.exports = {
    entry: './js/theme.js',
    output: {
        filename: 'theme.js',
        path: path.resolve(__dirname, 'pymedphys_sphinxtheme/static/js')
    }
};