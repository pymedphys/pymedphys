describe("When running in basic demo mode", () => {
    before(() => {
        cy.start("wlutz")
        cy.checkbox("Demo Mode")
    });

    it("should have three buttons", () => {  // More of a hello world test...
        cy.get(".stButton").should("have.length", 3);
    });
});
