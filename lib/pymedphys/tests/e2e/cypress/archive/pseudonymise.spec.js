/**
 * @license
 * Copyright 2018-2020 Streamlit Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
const path = require('path')

const fileName1 = "RS.1.2.840.10008.5.1.4.1.1.481.3.1591744445_Anonymised.dcm";
const fileName2 = "CT.1.3.12.2.1107.5.1.4.115496.30000017121402274359200000404_Anonymised.dcm";

describe("st.file_uploader", () => {
  // with respect to the current working folder
  const downloadsFolder = 'cypress/downloads'

  beforeEach(() => {
    cy.start("pseudonymise")
  });

  it('downloads remote zip', {}, () => {
    // image comes from a domain different from the page
    // cy.request({
    //   url:'https://zenodo.org/record/3887286/files/dummy-ct-and-struct.zip',
    //   timeout: 300000,
    //   encoding: 'binary',
    // })
    // .then((response) => {
    //   cy.writeFile(downloadsFolder+'/dummy-ct-and-struct.zip.b64', response.body, 'binary')
    //   cy.exec('base64 -d < ' + downloadsFolder+'/dummy-ct-and-struct.zip.b64' + ' > ' + downloadsFolder + '/dummy-ct-and-struct.zip')
    //   cy.exec('unzip -d ' + downloadsFolder + ' ' +  downloadsFolder+'/dummy-ct-and-struct.zip')
    // })

    //cy.log('**confirm downloaded zip**')
    //const downloadedFilename = path.join(downloadsFolder, 'dummy-ct-and-struct.zip')

    // // ensure the file has been saved before trying to parse it
    // cy.readFile(downloadedFilename, 'binary', { timeout: 15000 })
    // .should((buffer) => {
    //   // by having length assertion we ensure the file has text
    //   // since we don't know when the browser finishes writing it to disk

    //   // Tip: use expect() form to avoid dumping binary contents
    //   // of the buffer into the Command Log
    //   expect(buffer.length).to.be.gt(1000)
    // })
  })
  it("shows widget correctly", () => {

    // From https://github.com/streamlit/streamlit/blob/a03d3b9ae3c43a63b149dd590f8f6cf17ec917dd/e2e/specs/st_file_uploader.spec.js#L33
    cy.get("[data-testid='stFileUploader']")
      .first()
      .should("exist");
    cy.get("[data-testid='stFileUploader'] label")
      .first()
      .should("have.text", "Files to pseudonymise, refresh page after downloading zip(s)");

    // cy.get(".stFileUploader")
    //   .first()
    //   .matchImageSnapshot("single_file_uploader");

    // cy.get(".stFileUploader")
    //   .last()
    //   .matchImageSnapshot("multi_file_uploader");
  });

  // it("shows deprecation warning", () => {
  //   cy.get(".stFileUploader")
  //     .first()
  //     .parent()
  //     .prev()
  //     .should("contain", "FileUploaderEncodingWarning");
  // });

  it("hides deprecation warning", () => {
    cy.get("[data-testid='stFileUploader']")
      .last()
      .parent()
      .prev()
      .should("not.contain", "FileUploaderEncodingWarning");
  });

  // it("shows error message for not allowed files", () => {
  //   const fileName = "example.json";

  //   cy.fixture(fileName).then(fileContent => {
  //     cy.get(".fileUploadDropzone")
  //       .first()
  //       .upload(
  //         { fileContent, fileName, mimeType: "application/json" },
  //         {
  //           force: true,
  //           subjectType: "drag-n-drop",

  //           // We intentionally omit the "dragleave" trigger event here;
  //           // the page may start re-rendering after the "drop" event completes,
  //           // which causes a cypress error due to the element being detached
  //           // from the DOM when "dragleave" is emitted.
  //           events: ["dragenter", "drop"]
  //         }
  //       );

  //     cy.get(".fileError span")
  //       .first()
  //       .should("have.text", "application/json files are not allowed.");

  //     cy.get(".stFileUploader")
  //       .first()
  //       .matchImageSnapshot("file_uploader-error");
  //   });
  // });

  it("uploads single file only", () => {
    // Yes, this actually is the recommended way to load multiple fixtures
    // in Cypress (!!) using Cypress.Promise.all is buggy. See:
    // https://github.com/cypress-io/cypress-example-recipes/blob/master/examples/fundamentals__fixtures/cypress/integration/multiple-fixtures-spec.js
    cy.fixture(fileName1).then(file1 => {
      //  cy.fixture(fileName2).then(file2 => {
      const files = [
        { fileContent: file1, fileName: fileName1, mimeType: "application/octet-stream" },
        //   { fileContent: file2, fileName: fileName2, mimeType: "application/octet-stream" }
      ];

      // From https://github.com/streamlit/streamlit/blob/a03d3b9ae3c43a63b149dd590f8f6cf17ec917dd/e2e/specs/st_file_uploader.spec.js#L69
      cy.get("[data-testid='stFileUploadDropzone']")
        .eq(0)
        .attachFile(files[0], {
          force: true,
          subjectType: "drag-n-drop",
          events: ["dragenter", "drop"]
        });

      //       // The script should have printed the contents of the two files
      //       // into an st.text. (This tests that the upload actually went
      //       // through.)
      //       // cy.get(".uploadedFileName").should("have.text", fileName1);
      //       // cy.get(".fixed-width.stText")
      //       //   .first()
      //       //   .should("contain.text", file1);

      // cy.get(".stFileUploader")
      //   .first()
      //   .matchImageSnapshot("single_file_uploader-uploaded");

      // cy.get(".fileUploadDropzone")
      //   .eq(0)
      //   .attachFile(files[1], {
      //     force: true,
      //     subjectType: "drag-n-drop",
      //     events: ["dragenter", "drop"]
      //   });

      cy.get(".uploadedFileName")
        .should("have.text", fileName1);
      //.should("not.have.text", fileName1);
      // cy.get(".fixed-width.stText")
      //   .first()
      //   .should("contain.text", file2)
      //   .should("not.contain.text", file1);
      //});
    });
  });

  it("uploads multiple files", () => {

    // Yes, this actually is the recommended way to load multiple fixtures
    // in Cypress (!!) using Cypress.Promise.all is buggy. See:
    // https://github.com/cypress-io/cypress-example-recipes/blob/master/examples/fundamentals__fixtures/cypress/integration/multiple-fixtures-spec.js
    cy.fixture(fileName1).then(file1 => {
      cy.fixture(fileName2).then(file2 => {
        const files = [
          { fileContent: file1, fileName: fileName1, mimeType: "application/octet-stream" },
          { fileContent: file2, fileName: fileName2, mimeType: "application/octet-stream" }
        ];

        cy.get("[data-testid='stFileUploadDropzone']")
          .eq(0)
          .attachFile(files[0], {
            force: true,
            subjectType: "drag-n-drop",
            events: ["dragenter", "drop"]
          }).attachFile(files[1], {
            force: true,
            subjectType: "drag-n-drop",
            events: ["dragenter", "drop"]
          });

        // The widget should show the names of the uploaded files in reverse
        // order
        const filenames = [fileName2, fileName1];
        cy.get(".uploadedFileName").each((uploadedFileName, index) => {
          cy.get(uploadedFileName).should("have.text", filenames[index]);
        });

        // The script should have printed the contents of the two files
        // into an st.text. (This tests that the upload actually went
        // through.)
        // const content = [file1, file2].sort().join("\n");
        // cy.get(".fixed-width.stText")
        //   .last()
        //   .should("have.text", content);

        // cy.get(".stFileUploader")
        //   .last()
        //   .matchImageSnapshot("multi_file_uploader-uploaded");
      });
    });
  });

  it("Pseudonymises data", () => {
    cy.get(".stButton button").contains("Pseudonymise").click({ force: true });
    cy.compute();
    // having difficulty getting the sidebar.
    // ".sidebar" doesn't work.
    // div.reportview-container.section.sidebar
    // cy.get(".sidebar").contains(/^.+\.zip$/gm)
  });

});
