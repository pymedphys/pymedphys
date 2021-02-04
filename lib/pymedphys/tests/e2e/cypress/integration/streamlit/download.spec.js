/// <reference types="cypress" />
const path = require('path')

describe("When running the demo downloads app", () => {
    const downloadsFolder = 'cypress/downloads'

    before(() => {
        cy.start("download")
    });

    it("should be able to download `download.py` and have the appropriate copyright header.", () => {
        cy.get('a').contains('Click to download').click()
        const filename = path.join(downloadsFolder, 'download.py')

        cy.readFile(filename).should((text) => {
            const lines = text.split('\n')
            expect(lines[0]).to.contain("# Copyright (C) 2021 Cancer Care Associates")
        })
    });
});
