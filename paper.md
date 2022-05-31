---
title: "PyMedPhys: A community effort to develop an open standard library for Medical Physics in Python"
tags:
  - Python
  - Medical Physics
  - Radiation Therapy
  - Diagnostic Imaging
  - DICOM
authors:
  - name: Simon Biggs
    affiliation: 1
  - name: Matthew Jennings
    affiliation: 2
  - name: Stuart Swerdloff
    affiliation: 3
  - name: Phillip Chlap
    affiliation: "4, 5"
  - name: Derek Lane
    affiliation: 6
  - name: Jacob Rembish
    affiliation: 7
  - name: Jacob McAloney
    affiliation: 8
  - name: Paul King
    affiliation: 9
  - name: Rafael Ayala
    affiliation: 10
  - name: Fada Guan
    affiliation: 11
  - name: Nicola Lambri
    affiliation: "12, 13"
  - name: Cody Crewson
    affiliation: 14
  - name: Matthew Sobolewski
    affiliation: "8, 15"
affiliations:
  - name: Radiotherapy AI, Australia
    index: 1
  - name: Royal Adelaide Hospital, Australia
    index: 2
  - name: ELEKTA Pty Ltd, New Zealand
    index: 3
  - name: University of New South Wales, Australia
    index: 4
  - name: Ingham Institute, Australia
    index: 5
  - name: Elekta AB
    index: 6
  - name: NYU Langone Health, USA
    index: 7
  - name: Riverina Cancer Care Centre, Australia
    index: 8
  - name: Painless Skin Cancer Treatment, Mississippi, USA
    index: 9
  - name: Hospital G.U. Gregorio Marañón, Spain
    index: 10
  - name: Yale University School of Medicine, USA
    index: 11
  - name: IRCCS Humanitas Research Hospital, Italy
    index: 12
  - name: Humanitas University, Italy
    index: 13
  - name: Saskatchewan Cancer Agency, Canada
    index: 14
  - name: CancerCare Partners, Australia
    index: 15
date: 10 February 2022
bibliography: paper.bib
---

# Summary

PyMedPhys is an open-source medical physics Python library built by a community
that values and prioritizes code sharing, review, improvement, and peer
development. The overall goal of PyMedPhys is to provide medical physicists
around the world with a free, open-source library of Python applications to
simplify and enhance both their research and clinical work. It is inspired by
the collaborative work of our physics peers in astronomy and the Astropy
Project [@astropy].

# Statement of need

Medical radiation applications are subject to fast-paced technological
advancements. This is particularly true in the field of radiation oncology,
where the implementation of increasingly sophisticated technologies requires
increasingly complex processes to maintain the improving standard of care. To
help address this challenge, software tools that improve the quality, safety
and efficiency of clinical tasks are increasingly being developed in-house.
Commercial options are often prohibitively expensive or insufficiently tailored
to an individual clinic's needs. On the other hand, in-house development
efforts are often limited to a single institution. Similar tools that could
otherwise be shared are instead "reinvented" in clinics worldwide on a routine
basis. Moreover, individual institutions typically lack the personnel and
resources to incorporate simple aspects of good development practice or to
properly maintain in-house software.

By creating and promoting an open-source repository, PyMedPhys aims to improve
the quality and accessibility of existing software solutions to problems faced
across a range of medical radiation applications, especially those
traditionally within the remit of medical physicists. PyMedPhys is currently
implemented around the world for a handful of applications.
Many parties have embraced the gamma analysis module [@galic2020method;
@pastor2021learning; @rodriguez2020new; @spezialetti2021using; @castle2022;
@tsuneda2021plastic; @cronholm2020mri; @milan2019evaluation;
@gajewski2021commissioning; @lysakovski2021development], while implementations
of the electron cutout factor module and others [@baltz2021validation;
@rembish2021automating; @douglass2021deepwl] have also been reported.
Additionally, the work has been recognized by the European Society for
Radiotherapy and Oncology (ESTRO) and referenced as recommended literature in
their 3rd Edition of Core Curriculum for Medical Physics Experts in
Radiotherapy [@bertcatharine].

# Acknowledgements

We acknowledge the support of all who have contributed to the development of
PyMedPhys along the way.

# References
