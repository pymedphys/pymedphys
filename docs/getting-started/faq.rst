################################
Frequently Asked Questions (FAQ)
################################

***********************************
I need help! How do I ask for help?
***********************************

If you are having trouble, we are more than happy to help! The best way to seek
assistance from us is to raise an issue within the `PyMedPhys issue tracker`_
on GitHub. You will need to make a GitHub account to do this, but making an
account is very easy and almost certainly worth your while.

GitHub issues are preferable to email correspondence, since other people may
have similar questions. They might be able to get help from the same
answers/guidance that we provide to you.

Also, if you do find a question and answer within GitHub that you found
helpful, please notify us by commenting on the relevant issue and we will
consider adding it to the FAQ!


******************************************
How do I report a bug or provide feedback?
******************************************

Please raise an issue on GitHub within the `PyMedPhys issue tracker`_.
This is preferable to email correspondence, since GitHub issues are very
visible to all of the PyMedPhys contributors, any of whom can then address the
issue. It will also be visible to users who may either have the same issues or
be able to provide further perspective on the issue.

.. _`PyMedPhys issue tracker`: https://github.com/pymedphys/pymedphys/issues


*********************
How can I contribute?
*********************

We would love to have you be a part of the team! Please see our
`Developer Guide`_ to get started.

.. _`Developer Guide`: ../developer/contributing.html


****************************************
Can I do whatever I like with PyMedPhys?
****************************************

No. PyMedPhys is licensed under the AGPLv3+ license. Any usage or distribution
of PyMedPhys must comply with this license. See
`PyMedPhys licensing documentation`_ for more information.

.. _`PyMedPhys licensing documentation`: licensing.html


************************************************************************
Can I use the PyMedPhys CLI within a commercial, closed-source, product?
************************************************************************

Yes, you can. We have written our CLI in such a way that complex internal
data structures are not exposed. As such, if the only way your code interfaces
with PyMedPhys is via the CLI we have exposed then your program can be
considered a separate program, not a derivative. Any distribution of your
program with PyMedPhys will need to include the source code of PyMedPhys as
well as any changes you have made to PyMedPhys, but it will not need to include
the source of your commercial product. This is considered a "Mere Aggregation"
by the AGPL-3.0 license.

We believe even for a commercial entity `there is value in you embracing open
source for the code you write <../developer/agpl-benefits.html>`_, but to use
the PyMedPhys CLI within your products you don't have to.

For more information on this exception see the description of `Mere Aggregation
within the GPL FAQ
<https://www.gnu.org/licenses/gpl-faq.html#MereAggregation>`_ or the definition
of "aggregate" within `Section 5 of the AGPL license
<https://www.gnu.org/licenses/agpl-3.0.en.html#section5>`_.


What if what I want to use doesn't have a CLI?
==============================================

There are pathways available to you to have PyMedPhys include a CLI specific
to what you want. To achieve this you will either need to make a feature
request, or more effectively, write the CLI yourself and create a pull request.

To make a feature request use the `PyMedPhys issue tracker`_. To make a pull
request see the `Developer Guide`_ for how to begin.


************************************
How do I decode Elekta TRF logfiles?
************************************

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
