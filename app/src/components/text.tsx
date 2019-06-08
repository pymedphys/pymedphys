import React from 'react';

import {
  H2, H3
} from '@blueprintjs/core';

import demoFiles from '../data/demo-files.zip';

export class AppText extends React.Component {
  render() {
    return (
      <div>
        <H2>Overview</H2>

        <H3>Aim of application</H3>
        <p>
          In its current form this application takes a single Elekta Linac trf
          logfile as well as a single RT DICOM plan file that corresponds to
          the same plan as the logfile. It then process this data and creates
          the following:
        </p>
        <ul>
          <li>Decoded header and table csv files for the logfile</li>
          <li>
            The logfile mapped to a RT DICOM plan file using the provided
            DICOM file as a template (in ALPHA)
        </li>
          <li>
            A plot of the MU Density comparison between the logfile and the
            provided DICOM file
        </li>
        </ul>
        <p>
          In the future it is expected that this application will be able to
          serve as a generic file processing application for a range processing
          tasks.
        </p>

        <H3>Currently only works in Desktop Browsers</H3>
        <p>
          As far as has been tested thus far, this will only work in desktop
          browsers, only the desktop versions of Firefox and Chrome have been
          tested. On mobile browsers it the "Python Loading" will likely
          indefinitely hang.
        </p>

        <H3>Dependencies used</H3>
        <p>
          This is an example application that
        combines <a href="https://github.com/pymedphys/pymedphys/">
            PyMedPhys
        </a> with <a href="https://github.com/iodide-project/pyodide">
            pyodide
        </a>.
        </p>
        <p>
          This application loads Python into the <a href="https://webassembly.org/">
            wasm virtual machine
        </a> of your browser allowing Python code to be run on your local machine without
          having Python installed, or without needing Python to run on a remote server.</p>
        <p>
          When it comes to sensitive information or large data files, this
          means no data needs to leave your computer, while you still get the
          convenience a web app brings in not needing to install anything on
          your PC.
        </p>
        <p>
          Expect this application to freeze up, and not always work as
          expected. Both the application itself, and a key part of
          the engine that makes it work is under very much an ALPHA level of
          release. In practice this means feel free to use this application
          as a means to investigate what is possible, but do not rely on it
          to work correctly, or work at all.
       </p>

        <H2>Instructions for use</H2>
        <p>
          To begin, download <a href={demoFiles} type="application/zip">
            demo-files.zip
          </a>.
        </p>
        <p>
          Then, press browse below under File Management and select the .trf
          and .dcm files.
        </p>
        <p>
          Once these files have appeared within the input directory displayed
          then press "Process Files". At this point in time, unfortunately,
          the application will freeze until the processing is complete.
        </p>
        <p>
          Once the processing is complete, and the files appear within the
          output directory, press "Save Output" to download a zip of the
          contents of the output directory.
        </p>
      </div >
    )
  }
}