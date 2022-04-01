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
  - name: Stuart Swerdloff
    affiliation: 2
  - name: Matthew Jennings
    affiliation: 3
  - name: Phillip Chlap
    affiliation: "4, 5"
  - name: Jacob Rembish
    affiliation: 6
  - name: Jacob McAloney
    affiliation: 7
  - name: Paul King
    affiliation: 8
  - name: Rafael Ayala
    affiliation: 10
  - name: Matthew Sobolewski
    affiliation: "7, 9"
affiliations:
  - name: Radiotherapy AI, Australia
    index: 1
  - name: ELEKTA Pty Ltd, New Zealand
    index: 2
  - name: Royal Adelaide Hospital, Australia
    index: 3
  - name: University of News South Wales, Australia
    index: 4
  - name: Ingham Institute, Australia
    index: 5
  - name: NYU Langone Health, USA
    index: 6
  - name: Riverina Cancer Care Centre, Australia
    index: 7
  - name: Painless Skin Cancer Treatment, Mississippi, USA
    index: 8
  - name: CancerCare Partners, Australia
    index: 9
  - name: Hospital G.U. Gregorio Marañón, Spain
    index: 10  
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

As the treatment delivery methods used in radiation oncology continue to
improve, the complexity associated with ensuring precise and accurate delivery
continues to increase. In response, many medical physicists are turning toward
software solutions to help maximize efficiency and quality of care. It is
common for medical physicists to develop their own in-house code for performing
clinical tasks; many of which have been standardized through recommendations by
organizations such as the American Association of Physicists in Medicine
(AAPM). This can often lead to the "reinvention of the wheel", where physicists
are wasting time writing code to serve a purpose that someone else has already
accomplished.

By creating and promoting an open-source repository, PyMedPhys aims to improve
the quality and accessibility of exisiting software solutions to problems faced by
medical physicists. PyMedPhys is currently implemented around the world for a handful of
applications. Many parties have embraced the gamma analysis module
[@galic2020method; @pastor2021learning; @rodriguez2020new;
@spezialetti2021using; @castle2022; @tsuneda2021plastic; @cronholm2020mri;
@milan2019evaluation; @gajewski2021commissioning; @lysakovski2021development],
while implementations of the electron cutout factor module and others [@baltz2021validation;
@rembish2021automating; @douglass2021deepwl] have also been reported. Additionally, the work has been recognized by the European
Society for Radiotherapy and Oncology (ESTRO) and referenced as recommended
literature in their 3rd Edition of Core Curriculum for Medical Physics Experts
in Radiotherapy [@bertcatharine].

# Acknowledgements

We acknowledge the support of all who have contributed to the development of
PyMedPhys along the way.

# References
