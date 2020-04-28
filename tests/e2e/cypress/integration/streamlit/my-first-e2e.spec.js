/// <reference types="cypress" />

describe("smoke", () => {
  beforeEach(() => {
    cy.visit("http://localhost:8501/");
    cy.get(".decoration").invoke("css", "display", "none");
  });

  it("basics", () => {
    cy.get(".stTextInput input")
      .first()
      .type("989898{enter}");

    cy.get("#ReportStatus").should("not.be.visible")

    cy.get(".stMarkdown").contains('MU')
  });
});
