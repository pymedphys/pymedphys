/// <reference types="cypress" />

describe("When running the electrons app with the demo config", () => {

  before(() => {
    cy.start("electrons")
    cy.radio("Config file to use", "Demo")
  });

  it("should be able to have the calculated factor match baseline.", () => {
    cy.radio("Monaco Plan Location", "RED")

    cy.get(".stTextInput input")
      .first()
      .type("989898{enter}");
    cy.compute()

    cy.radio("Select a Monaco plan", "Electron")
    cy.get(".stButton button")
      .contains("Calculate")
      .click()
    cy.compute()

    cy.textMatch('Factor', 1, '1.0571')
  });
});
