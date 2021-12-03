/// <reference types="cypress" />


describe("When pressing the status button", () => {
  before(() => {
    cy.start("metersetmap")
    cy.radio("Config Mode", "Demo")

    cy.get(".stButton button").contains("Check status").click()

    cy.compute()
  });

  it("should have 2 fields that contain George:", () => {
    cy.textMatch('George', 2, null)
  });

  it("should have 2 fields that contain MacDonald:", () => {
    cy.textMatch('MacDonald', 2, null)
  });
});


describe("When using a Patient ID of 979797 in BLUE clinic and selecting the last iCOM record", () => {
  before(() => {
    cy.start("metersetmap")
    cy.radio("Config Mode", "Demo")

    cy.radio("Monaco Plan Location", "BLUE")

    cy.get(".stTextInput input")
      .first()
      .type("979797{enter}");
    cy.compute()

    cy.get(".stMultiSelect")
      .first()
      .type("2020-04-29 07:50:43{enter}")
    cy.compute()
  });

  it("should have 4 fields that read Total MU: 426.7", () => {
    cy.textMatch('Total MU', 4, '426.7')
  });

  it("should have 3 fields that read Patient Name: PHYSICS, Test", () => {
    cy.textMatch('Patient Name', 3, 'PHYSICS, Test')
  });
});


describe("When using a Patient ID of 989898 in RED clinic and selecting the last iCOM record", () => {
  before(() => {
    cy.start("metersetmap")
    cy.radio("Config Mode", "Demo")

    cy.get(".stTextInput input")
      .first()
      .type("989898{enter}");
    cy.compute()

    cy.radio("Select a Monaco plan", "3ABUT")

    cy.get(".stMultiSelect")
      .first()
      .type("2020-04-29 07:47:29{enter}")
    cy.compute()
  });

  it("should have 4 fields that read Total MU: 150.0", () => {
    cy.textMatch('Total MU', 4, '150.0')
  });

  it("should have 3 fields that read Patient Name: PHYSICS, Mock", () => {
    cy.textMatch('Patient Name', 3, 'PHYSICS, Mock')
  });
});


describe("When using a Patient ID of 989898 in RED clinic and selecting the second two iCOM records", () => {
  before(() => {
    cy.start("metersetmap")
    cy.radio("Config Mode", "Demo")

    cy.get(".stTextInput input")
      .first()
      .type("989898{enter}");
    cy.compute()

    cy.radio("Select a Monaco plan", "3ABUT")

    cy.get(".stMultiSelect")
      .first()
      .type("2020-04-29 07:45:59{enter}2020-04-29 07:44:44{enter}")
    cy.compute()
  });

  it("should have 4 fields that read Total MU: 150.0", () => {
    cy.textMatch('Total MU', 4, '150.0')
  });

  it("should have 3 fields that read Patient Name: PHYSICS, Mock", () => {
    cy.textMatch('Patient Name', 3, 'PHYSICS, Mock')
  });
});


describe("When running all calculations", () => {
  before(() => {
    cy.start("metersetmap")
    cy.radio("Config Mode", "Demo")
  });
  it("should have output files that agree with the baseline data", { retries: 3 }, () => {
    cy.get(".stCheckbox").contains("Run in Advanced Mode").click();
    cy.compute()

    cy.get(".stTextInput input")
      .first()
      .type("989898{enter}");
    cy.compute()

    cy.radio("Select a Monaco plan", "3ABUT")

    cy.get(".stMultiSelect")
      .first()
      .type("2020-04-29 07:47:29{enter}")
    cy.compute()

    cy.get(".stButton button").contains("Run Calculation").click()
    cy.finalScreenshot()

    cy.get(".stSelectbox").first().type("DICOM RTPlan file upload{enter}")
    cy.compute()

    cy.radio("DICOM import method", "Search Monaco")
    cy.radio("Monaco Export Location", "BLUE")

    cy.get(".stTextInput input")
      .first()
      .type("979797{enter}");
    cy.compute()

    cy.get(".stMultiSelect")
      .first()
      .type("2020-04-29 07:50:43{enter}")
    cy.compute()

    cy.get(".stButton button").contains("Run Calculation").click()
    cy.finalScreenshot()

    cy.get(".stButton button").contains("Compare Baseline to Output Directory").click()

    cy.compute()
    cy.scroll()
    cy.screenshot()

    cy.textMatch('Images Agree', 8, 'True')
  });
});
