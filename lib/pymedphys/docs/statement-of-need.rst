=====================
Statement of Need
=====================

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
traditionally within the remit of medical physicists. These solutions can be
broadly categorised in two areas: data extraction/conversion of proprietary
formats from a variety of radiotherapy systems, and manipulation of standard
radiotherapy data to perform quality assurance (QA) tasks that are otherwise
time-consuming or lack commercial solutions with the desired flexibility or
true function.

Data extraction and conversion currently includes: two treatment planning
systems, an oncology information system, and a linear accelerator vendor
family of systems. Data in proprietary formats from these systems are
extracted and converted to allow for integration in a myriad of applications.
Applications that use planning system information include: electron cut-out
factor determination, CT extension, and extraction of dose information for
patient QA purposes. Applications that use the oncology information systems
include: clinical dashboards that summarise data, quality task tracking, and
comparison of dose information to planning systems. Applications that use the
linear accelerator data include: patient specific QA analysis against planning
data, and analysis of machine performance such as the Winston-Lutz test.

QA tasks using standard radiotherapy data include: anonymisation, extraction
of dose data for analysis, manipulation of contour files to allow merging or
adjustments/scaling of relative electron density, modifying machine names
in plans, and most frequently used, the calculation of a Gamma index, a widely
recognised metric in radiotherapy analysis that quantifies the difference
between measured and calculated dose distributions on a point-by-point basis
in terms of both dose and distance to agreement (DTA) differences.

Many of these tools are in use clinically at affiliated sites, and
additionally, aspects of PyMedPhys are implemented around the world for some
applications. Many parties have embraced the gamma analysis module,
while implementations of the electron cutout factor module and others have also
been reported. Additionally, the work has been recognized by the European
Society for Radiotherapy and Oncology (ESTRO) and referenced as recommended
literature in their 3rd Edition of Core Curriculum for Medical Physics Experts
in Radiotherapy.
