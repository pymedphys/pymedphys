/// <reference types="cypress" />

describe("st.button", () => {
  beforeEach(() => {
    cy.visit("http://localhost:5201/");
  });

  it("basics", () => {
    cy.get(".stButton").should("have.length", 1);

    cy.get(".stButton").matchImageSnapshot("button-widget");
  });
});
