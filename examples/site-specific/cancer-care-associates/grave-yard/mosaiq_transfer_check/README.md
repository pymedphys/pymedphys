# Overview

This is a tool that compares the field delivery parameters at NBCCC to those
delivered at RCCC while taking the IMRT QA measurement on the Delta4.

# Further details

Our company has two Cancer Centres, one in Sydney and one in Wagga Wagga.
Due to the distance and current unreliability of the NBN we have two separate
instances of Mosaiq, one for each site. All machines at both centres are beam
matched. Therefore given that ongoing QA for each machine is up to date IMRT
QA which is planned on our planning systems is able to undergo QA on any of
our machines.

However, should IMRT QA be undergone at one centre on one instance of Mosaiq,
and should the delivery be undergone on a different instance of Mosaiq there
is the need for a treatment plan data parity check between the two Mosaiq
systems.

This is a python tool that exports the beam parameters from each Mosaiq SQL
database, stores these beam parameters within CSV files for documentation and
tool independent verification, the stored exported data is then directly
compared and a patient specific report is created documenting that the beams
within the OIS used for IMRT QA matches the beams within the OIS used for
delivery.
