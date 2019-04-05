================================
Frequently Asked Questions (FAQ)
================================


I need help! How do I ask for help?
-----------------------------------

If you are having trouble, we are more than happy to help! The best way to seek
assistance from us is to raise an issue within the
`PyMedPhys repo issues section`_
on GitHub. You will need to make a GitHub account to do this, but making an
account is very easy and almost certainly worth your while.

GitHub issues are preferable to email correspondence, since other people may
have similar questions. They might be able to get help from the same
answers/guidance that we provide to you.

Also, if you do find a question and answer within GitHub that you found
helpful, please notify us by commenting on the relevant issue and we will
consider adding it to the FAQ!


How do I report a bug or provide feedback?
-------------------------------------------

Please raise an issue on GitHub within the `PyMedPhys repo issues section`_.
This is preferable to email correspondence, since GitHub issues are very
visible to all of the PyMedPhys contributors, any of whom can then address the
issue. It will also be visible to users who may either have the same issues or
be able to provide further perspective on the issue.

.. _`PyMedPhys repo issues section`: https://github.com/pymedphys/pymedphys/issues


How can I contribute?
---------------------

We would love to have you be a part of the team! Please see our
`Developer Guide`_ to get started.

.. _`Developer Guide`: ../developer/contributing.html


Can I do whatever I like with PyMedPhys?
----------------------------------------

No. PyMedPhys is licensed under the AGPLv3+ license. Any usage or distribution
of PyMedPhys must comply with this license. See
`PyMedPhys licensing documentation`_ for more information.

.. _`PyMedPhys licensing documentation`: licensing.html


How do I decode Elekta TRF logfiles?
------------------------------------

If all you want to do is convert the ``.trf`` format to a human readable
``.csv`` format, then using the trf command line interface (CLI) tool should be
sufficient. You'll initially need to install PyMedPhys (with help from the
`PyMedPhys installation documentation`_). You'll then be able to open a command
prompt and use the `Elekta Binary logfile to csv CLI`_.

.. _`PyMedPhys installation documentation`: installation.html

.. _`Elekta binary logfile to csv CLI`: ../user/interfaces/cli/trf.html#to-csv

A larger project within PyMedPhys is underway that involves not only decoding
these logfiles, but then indexing them by patient name and achieving other QA
related tasks. For an overview of this project, see the
`Elekta logfile decoding and indexing project`_.

.. _`Elekta logfile decoding and indexing project`: ../projects/elekta-logfiles.html
