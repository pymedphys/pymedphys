// ***********************************************
// This example commands.js shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************
//
//
// -- This is a parent command --
// Cypress.Commands.add("login", (email, password) => { ... })
//
//
// -- This is a child command --
// Cypress.Commands.add("drag", { prevSubject: 'element'}, (subject, options) => { ... })
//
//
// -- This is a dual command --
// Cypress.Commands.add("dismiss", { prevSubject: 'optional'}, (subject, options) => { ... })
//
//
// -- This will overwrite an existing command --
// Cypress.Commands.overwrite("visit", (originalFn, url, options) => { ... })

// import { addMatchImageSnapshotCommand } from 'cypress-image-snapshot/command';

// addMatchImageSnapshotCommand();

import 'cypress-file-upload';


Cypress.Commands.add('compute', () => {
  let start = new Date().getTime();
  cy.get("#ReportStatus", { timeout: 4000 }).should($el => {
    let now = new Date().getTime();
    if (now - start < 1000) {
      expect($el).to.be.visible
    } else {
      expect($el).to.not.be.visible
    }
  })

  cy.get("#ReportStatus", { timeout: 120000 }).should("not.be.visible")
})

Cypress.Commands.add('textMatch', (label, length, result) => {
  let text = cy.get(`.stMarkdown p:contains(${label})`).should("have.length", length)
  if (result !== null) {
    text.find('code').each(($el) => {
      return cy.wrap($el).should("have.text", result)
    })
  }
})

Cypress.Commands.add('start', (app) => {
  cy.visit('http://localhost:8501')

  Cypress.Cookies.defaults({
    preserve: ["_xsrf"]
  });

  cy.visit(`http://localhost:8501/?app=${app}`);
  cy.compute()

  // From https://github.com/streamlit/streamlit/blob/a03d3b9ae3c43a63b149dd590f8f6cf17ec917dd/e2e/specs/component_template.spec.js#L41-L42
  // Make the ribbon decoration line disappear
  cy.get("[data-testid='stDecoration']").invoke("css", "display", "none");
})


Cypress.Commands.add('scroll', () => {
  cy.get(".main").scrollTo("bottomLeft");
})

Cypress.Commands.add('finalScreenshot', () => {
  cy.scroll()
  cy.compute()
  cy.scroll()
  cy.compute()
  cy.scroll()
  cy.screenshot()
})
