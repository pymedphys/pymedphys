module.exports = function (grunt) {

  // load all grunt tasks
  require('matchdep').filterDev('grunt-*').forEach(grunt.loadNpmTasks);

  grunt.initConfig({
    // Read package.json
    pkg: grunt.file.readJSON("package.json"),

    open: {
      dev: {
        path: 'http://localhost:1919'
      }
    },

    connect: {
      server: {
        options: {
          port: 1919,
          base: 'docs/build',
          livereload: true
        }
      }
    },
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
      dev: {
        options: {
          style: 'expanded',
          loadPath: ['bower_components/bourbon/dist', 'bower_components/neat/app/assets/stylesheets', 'bower_components/font-awesome/scss', 'bower_components/wyrm/sass']
        },
        files: [{
          expand: true,
          cwd: 'sass',
          src: ['*.sass'],
          dest: 'pymedphys_sphinxtheme/static/css',
          ext: '.css'
        }]
      },
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
      dev: {
        options: {
          external: ['jquery'],
          alias: {
            'sphinx-rtd-theme': './js/theme.js'
          }
        },
        src: ['js/*.js'],
        dest: 'pymedphys_sphinxtheme/static/js/theme.js'
      },
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
    uglify: {
      dist: {
        options: {
          sourceMap: false,
          mangle: {
            reserved: ['jQuery'] // Leave 'jQuery' identifier unchanged
          },
          ie8: true // compliance with IE 6-8 quirks
        },
        files: [{
          expand: true,
          src: ['pymedphys_sphinxtheme/static/js/*.js', '!pymedphys_sphinxtheme/static/js/*.min.js'],
          dest: 'pymedphys_sphinxtheme/static/js/',
          rename: function (dst, src) {
            // Use unminified file name for minified file
            return src;
          }
        }]
      }
    },
    usebanner: {
      dist: {
        options: {
          position: 'top',
          banner: '/* <%= pkg.name %> version <%= pkg.version %> | MIT license */\n' +
            '/* Built <%= grunt.template.today("yyyymmdd HH:mm") %> */',
          linebreak: true
        },
        files: {
          src: ['pymedphys_sphinxtheme/static/js/theme.js', 'pymedphys_sphinxtheme/static/css/theme.css']
        }
      }
    },
    exec: {
      bower_update: {
        cmd: 'bower update'
      },
      build_sphinx: {
        cmd: 'sphinx-build docs/ docs/build'
      }
    },
    clean: {
      build: ["docs/build"],
      fonts: ["pymedphys_sphinxtheme/static/fonts"],
      css: ["pymedphys_sphinxtheme/static/css"],
      js: ["pymedphys_sphinxtheme/static/js/*", "!pymedphys_sphinxtheme/static/js/modernizr.min.js"]
    },

    watch: {
      /* Compile sass changes into theme directory */
      sass: {
        files: ['sass/*.sass', 'bower_components/**/*.sass'],
        tasks: ['sass:dev']
      },
      /* Changes in theme dir rebuild sphinx */
      sphinx: {
        files: ['pymedphys_sphinxtheme/**/*', 'README.rst', 'docs/**/*.rst', 'docs/**/*.py'],
        tasks: ['clean:build', 'exec:build_sphinx']
      },
      /* JavaScript */
      browserify: {
        files: ['js/*.js'],
        tasks: ['browserify:dev']
      },
      /* live-reload the docs if sphinx re-builds */
      livereload: {
        files: ['docs/build/**/*'],
        options: { livereload: true }
      }
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

  grunt.registerTask('default', ['exec:bower_update', 'clean', 'copy:fonts', 'sass:dev', 'browserify:dev', 'usebanner']);
  grunt.registerTask('build', ['exec:bower_update', 'clean', 'copy:fonts', 'sass:build', 'browserify:build', 'uglify', 'usebanner']);
}
