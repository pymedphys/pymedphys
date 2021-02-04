/// <reference types="cypress" />
const path = require('path')

describe("When pressing the status button", () => {
    const downloadsFolder = 'cypress/downloads'

    before(() => {
        cy.start("download")
    });

    it("should have 2 fields that contain George:", () => {
        cy.get('a').contains('Click to download').click()
        const filename = path.join(downloadsFolder, 'downloads.py')

        cy.readFile(filename).should((text) => {
            const lines = text.split('\n')
            expect(lines[0]).to.equal("# Copyright (C) 2021 Cancer Care Associates")
        })
    });
});
