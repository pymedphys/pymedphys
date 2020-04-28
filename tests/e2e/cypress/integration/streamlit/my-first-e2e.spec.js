/// <reference types="cypress" />

Cypress.Commands.add('compute', () => {
  cy.get("#ReportStatus").should("be.visible")
  cy.get("#ReportStatus").should("not.be.visible")
})

Cypress.Commands.add('textMatch', (label, length, result) => {
  cy.get(`.stMarkdown p:contains(${label})`).should("have.length", length).find('code').each((el) => {
    cy.wrap(el).should("have.text", result)
  })
})


describe("smoke", () => {
  beforeEach(() => {
    cy.visit("http://localhost:8501/");
    cy.compute()
    cy.get(".decoration").invoke("css", "display", "none");
  });

  it("basics", () => {
    cy.get(".stTextInput input")
      .first()
      .type("989898{enter}");

    cy.compute()

    cy.get(".stMultiSelect")
      .first()
      .type("2020-04-29 07:47:29{enter}")

    cy.textMatch('Total MU', 4, '150.0')
    cy.textMatch('Patient Name', 3, 'PHYSICS, Mock')
  });
});
