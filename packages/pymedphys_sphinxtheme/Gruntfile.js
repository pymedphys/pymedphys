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
            src: ['bower_components/font-awesome/fonts/*'],
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
          style: 'compressed',
          sourcemap: 'none',
          loadPath: ['bower_components/bourbon/dist', 'bower_components/neat/app/assets/stylesheets', 'bower_components/font-awesome/scss', 'bower_components/wyrm/sass']
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

    exec: {
      bower_update: {
        cmd: 'bower update'
      }
    },

    clean: {
      build: ["docs/build"],
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

  grunt.registerTask('build', ['exec:bower_update', 'clean', 'copy:fonts', 'sass:build', 'browserify:build']);
}
