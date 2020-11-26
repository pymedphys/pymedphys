Benefits of Open Source for Medical Physics
===========================================

The aim of this document is to outline some of the benefits of Medical Physics
code being released under an open source license.

A summary of the license used by PyMedPhys and what it entails is available at
`choose a license <https://choosealicense.com/licenses/apache-2.0/>`_.

Software is less dependent on a single software developer
---------------------------------------------------------

A significant issue with software that is built by a small software development
team is the "bus factor". In the event that key team members are lost the
software is no longer able to be easily maintained. By opening the code up to
the community the number of people who understand the code base is increased.
This reduces the dependence on any single employee for the ongoing maintenance
of the code packages.

Additionally software development by single developers carry any weaknesses
that developer has as a programmer and its only strengths will be limited to
those of that programmer. Medical Physicists are generally not trained software
engineers, and when it comes to programming we often have many weaknesses that
need a light shined upon.

This was `the justification
<http://randlet.com/static/downloads/papers/QATrack+%20Odette%20Cancer%20Centre.pdf>`_
provided by the radiation therapy `QATrack+ team
<http://qatrackplus.com/>`_ for open sourcing their tools.

Safer and higher quality software
---------------------------------

By leveraging the community in software production there will be more minds,
more programmers, and more readers of the code. Together there will be more
combined time to implement software engineering best practices and there are
physicists in the community who are keen to support best practice software
engineering. The community will be able to fix bugs, implement programmatic
testing, highlight security issues, and generally all round produce safer and
higher quality software than a sole physicist turned programmer ever could.

Software that is more compatible with a wide range of systems
-------------------------------------------------------------

Users of open source code who are also programmers who have systems which
differ to the author’s will be able to improve compatibility issues themselves.
This iterative process with the community makes it so that the software has a
more seamless interaction with the range of systems in use.

An example of this is the `Pylinac quality assurance tool
<http://pylinac.readthedocs.io/en/latest/index.html>`_. It was built by a
physicist who works at a Varian site. Another physicist `submitted code
improvements <https://github.com/jrkerns/pylinac/pull/67>`_ to make the software
tool compatible with Elekta.

Improving our work as Physicists
--------------------------------

The software we write is written for the purpose of improving our work as
physicists. Having the community improve the software we write directly
improves the quality of the work we undergo.

Improving the programming skill of employees through community feedback
-----------------------------------------------------------------------

Programming skills are significantly benefited by having competent programmers
read the code and provide feedback. Community feedback on code itself is
invaluable for improving the skill of the programmers writing the original
code. The depth and breadth of feedback from the community on programming
practices would unable to be matched within a small team.

Software that has more applications and more features
-----------------------------------------------------

As members of the community have needs those with programming skill may extend
the code that is provided to meet those needs. This results in the code having
more applications and features than would be possible should the code be kept
in house.

Improvements will by default be in a compatible format
------------------------------------------------------

Should the community create code built on top of the released software tools,
those improvements will built on top of the format that is already implemented.
This allows those improvements to be integrated within already implemented
systems with minimal friction.
