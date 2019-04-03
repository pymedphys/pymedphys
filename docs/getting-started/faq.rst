================================
Frequently Asked Questions (FAQ)
================================


I need help, how do I ask for help?
-----------------------------------

If you are having trouble we would be more than happy to help. Please raise an
issue within the `PyMedPhys repo issues section`_ on GitHub. To do this you
will need to make a GitHub account, but this is not too dificult and it will
be worth your while.

This is preferable as opposed to sending an email, as others likely have similar
questions, and that means they might be able to get help from the same answers/guidance
we provide to you.

Also, if you do find a question and answer on GitHub that was helpful to you
it might be worth making a comment that the question and response should belong
within this FAQ document.


How can I report a bug or provide feedback?
-------------------------------------------

You can raise an issue on GitHub within the `PyMedPhys repo issues section`_.
Please use this as opposed to emailing contributors if possible as this means
the reports/questions/feedback is visible by others who potentially have the
same issues or might be able to provide further perspective on the issue.

.. _`PyMedPhys repo issues section`: https://github.com/pymedphys/pymedphys/issues


How can I contribute?
---------------------

We would love to have you be a part of the team. There is a guide to help
developers onboard to help contributing. See the `PyMedPhys contributor documentation`_.

.. _`PyMedPhys contributor documentation`: ../developer/contributing.html


Can I do whatever I like with PyMedPhys?
----------------------------------------

No. PyMedPhys is licensed under the AGPLv3+ license. Any usage or distribution
of PyMedPhys must comply with this license. See `PyMedPhys licensing documentation`_
for more information.

.. _`PyMedPhys licensing documentation`: licensing.html


Can I develop and sell closed source proprietary code that is a derivative of PyMedPhys?
----------------------------------------------------------------------------------------

You certainly can sell whatever you build on top of PyMedPhys. But the
requirement of any distribution (selling or for free), is that you also release
the source code of PyMedPhys and any derivative of
PyMedPhys under an AGPLv3.0+ license. So, because you have asked to distribute a **closed source** proprietary
derivative of PyMedPhys, the answer is no.

PyMedPhys was licensed in this way because one of the main aims of this project is
that we wish to create a toolbox which we all have access to today, and
we also all have access to whatever it becomes in the future. For further
information on this decision please see the `benefits of open source`_.

.. _`benefits of open source`: ../developer/agpl-benefits.html

It is understood however that this potentially may impede the uptake of PyMedPhys
for people who wish to build tools they might like to sell in a closed source
fashion one day. If you are in this boat, please reach out to the PyMedPhys
developers at developers@pymedphys.com. We also want PyMedPhys to be as useful
to as many people as it can be, and an arangement may be possible where the
aims of PyMedPhys are met, as well as your own.


How do I decode Elekta TRF logfiles?
------------------------------------

If all you want to do is convert the ``.trf`` format to a human readable ``.csv``
format then using the trf command line interface (CLI) tool should be sufficient.
You'll initially need to install PyMedPhys with help from the `PyMedPhys installation documentation`_
and then you can open a command prompt and use the `Elekta Binary logfile to csv CLI`_.

.. _`PyMedPhys installation documentation`: installation.html

.. _`Elekta binary logfile to csv CLI`: ../user-cli/trf.html#to-csv

There is a greater project that involves not only decoding these logfiles, but then
also indexing them by patient name and achieving other QA related tasks. To
see an overview of that project itself see the `Elekta lofgile decoding and indexing project`_.

.. _`Elekta lofgile decoding and indexing project`: ../projects/elekta-logfiles.html