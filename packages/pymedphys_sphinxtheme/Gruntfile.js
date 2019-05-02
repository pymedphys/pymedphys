module.exports = function (grunt) {

  // load all grunt tasks
  require('matchdep').filterDev('grunt-*').forEach(grunt.loadNpmTasks);

  grunt.initConfig({
    // Read package.json
    pkg: grunt.file.readJSON("package.json"),

    copy: {
      fonts: {
        files: [
          {
            expand: true,
            flatten: true,
            src: ['node_modules/font-awesome/fonts/*'],
            dest: 'pymedphys_sphinxtheme/static/fonts/',
            filter: 'isFile'
          },
          {
            expand: true,
            flatten: true,
            src: ['fonts/Lato/*'],
            dest: 'pymedphys_sphinxtheme/static/fonts/Lato',
            filter: 'isFile'
          },
          {
            expand: true,
            flatten: true,
            src: ['fonts/RobotoSlab/*'],
            dest: 'pymedphys_sphinxtheme/static/fonts/RobotoSlab/',
            filter: 'isFile'
          }
        ]
      }
    },

    sass: {
      build: {
        options: {
          style: 'expanded',
          sourcemap: 'none',
          loadPath: ['node_modules/bourbon/app/assets/stylesheets', 'node_modules/bourbon-neat/app/assets/stylesheets', 'node_modules/font-awesome/scss', 'node_modules/wyrm/sass']
        },
        files: [{
          expand: true,
          cwd: 'sass',
          src: ['*.sass'],
          dest: 'pymedphys_sphinxtheme/static/css',
          ext: '.css'
        }]
      }
    },

    browserify: {
      build: {
        options: {
          external: ['jquery'],
          alias: {
            'sphinx-rtd-theme': './js/theme.js'
          }
        },
        src: ['js/*.js'],
        dest: 'pymedphys_sphinxtheme/static/js/theme.js'
      }
    },

    clean: {
      fonts: ["pymedphys_sphinxtheme/static/fonts"],
      css: ["pymedphys_sphinxtheme/static/css"],
      js: ["pymedphys_sphinxtheme/static/js/*", "!pymedphys_sphinxtheme/static/js/modernizr.min.js"]
    }
  });

  grunt.loadNpmTasks('grunt-exec');
  grunt.loadNpmTasks('grunt-contrib-connect');
  grunt.loadNpmTasks('grunt-contrib-watch');
  grunt.loadNpmTasks('grunt-contrib-sass');
  grunt.loadNpmTasks('grunt-contrib-clean');
  grunt.loadNpmTasks('grunt-contrib-copy');
  grunt.loadNpmTasks('grunt-open');
  grunt.loadNpmTasks('grunt-browserify');

  grunt.registerTask('build', ['clean', 'copy:fonts', 'sass:build', 'browserify:build']);
}
