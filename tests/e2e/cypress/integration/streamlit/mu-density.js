/// <reference types="cypress" />

describe("When running the MU Density tool", () => {
  beforeEach(() => {
    cy.start()
  });

  it("a patient ID of 989898 should have 150.0 MU and be called PHYSICS, Mock", () => {
    cy.get(".stTextInput input")
      .first()
      .type("989898{enter}");

    cy.compute()

    cy.get(".stMultiSelect")
      .first()
      .type("2020-04-29 07:47:29{enter}")

    cy.compute()

    cy.textMatch('Total MU', 4, '150.0')
    cy.textMatch('Patient Name', 3, 'PHYSICS, Mock')
  });
});
