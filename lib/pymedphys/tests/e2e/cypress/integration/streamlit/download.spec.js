/// <reference types="cypress" />
const path = require('path')

describe("When running the demo downloads app", () => {
    const downloadsFolder = 'cypress/downloads'

    before(() => {
        cy.start("download")
    });

    it("should be able to download `download.py` and have the appropriate copyright header.", () => {
        cy.get('a').contains('download.py').click()
        const filename = path.join(downloadsFolder, 'download.py')

        cy.readFile(filename).should((text) => {
            const lines = text.split('\n')
            expect(lines[0]).to.contain("# Copyright (C) 2021 Cancer Care Associates")
        })
    });

    it("should be able to download `a_text_file.txt` and have the appropriate contents.", () => {
        cy.get('a').contains('a_text_file.txt').click()
        const filename = path.join(downloadsFolder, 'a_text_file.txt')

        cy.readFile(filename).should((text) => {
            expect(text).to.contain("Some beautiful text!")
        })
    });
});
