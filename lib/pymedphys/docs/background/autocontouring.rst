============================
Automatic Contouring Project
============================

Project aim
-----------

Accurate contouring is a critical aspect of safe and effective treatment
delivery in radiotherapy (RT). Current limitations in clinical practice include
large intra and inter-observer variances (IOV), as well as time delays in both
contour generation and correction. This study designed and evaluated a 2D U-Net
architecture with two primary aims:

1) Automate a time consuming aspect of canine radiotherapy. Specifically, vacuum
   bag segmentation has been reported to take approximately 30 minutes to
   contour manually.

2) Evaluate the ability of a 2D U-Net model to achieve expert level performance
   as defined by Nikolov et al.'s surface dice similarity coefficient [1]_ with
   respect to IOV.

The intent for this research is to act as a template for future work extending
to other organs.


Video Demonstrating Usage
-------------------------

Best viewed at 720p+ resolution.

.. raw:: html

    <embed><style>.embed-container { position: relative; padding-bottom:
    56.25%; height: 0; overflow: hidden; max-width: 100%; } .embed-container
    iframe, .embed-container object, .embed-container embed { position:
    absolute; top: 0; left: 0; width: 100%; height: 100%; }</style><div
    class='embed-container'><iframe
    src='https://www.youtube.com/embed/fMCv5i6GJWI' frameborder='0'
    allowfullscreen></iframe></div></embed>


Details
-------
The `Masters thesis
<https://github.com/matthewdeancooper/masters_thesis/blob/master/main.pdf>`_
developed during this software project has been publicly released to provide a
detailed description of the work. It provides details of the model architecture,
and examines performance under multiple loss functions. In addition, this work
discusses the development of a second model designed to fulfil the need for
contouring to become part of regular quality assurance testing.

Consider joining the PyMedPhys `mailing list
<https://groups.google.com/g/pymedphys?pli=1>`_ to be notified of future
progress on this topic.


Basic Implementation
--------------------

Details on how to implement the project into your own workflow will be provided
once the code migrates from the experimental division of PyMedPhys into the main
code base. Watch this space.


References
----------

.. [1] Nikolov et al. "Deep learning to achieve clinically applicable segmentation of head
    and neck anatomy for radiotherapy." (2018): https://arxiv.org/pdf/1809.04430.pdf
