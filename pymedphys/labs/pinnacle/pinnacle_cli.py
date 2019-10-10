# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.

# This work is derived from:
# https://github.com/AndrewWAlexander/Pinnacle-tar-DICOM
# which is released under the following license:

# Copyright (c) [2017] [Colleen Henschel, Andrew Alexander]

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# The following needs to be removed before leaving labs
# pylint: skip-file

import logging
import os
import sys
import tarfile
import tempfile

from .pinnacle import PinnacleExport


def export_cli(args):
    """
    expose a cli to allow export of Pinnacle raw data to DICOM objects
    """

    output_directory = args.output_directory
    verbose = args.verbose
    modality = args.modality
    plan_name = args.plan
    trial = args.trial
    list_available = args.list
    image_series = args.image
    uid_prefix = args.uid_prefix

    input_path = args.input_path

    # Create a logger to std out for cli
    log_level = logging.INFO
    logger = logging.getLogger(__name__)
    if verbose:
        log_level = logging.DEBUG
    logger.setLevel(log_level)

    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    ch.setLevel(log_level)
    logger.addHandler(ch)

    # If no modality given, export all modalities
    if len(modality) == 0:
        modality = ["CT", "RTSTRUCT", "RTDOSE", "RTPLAN"]

    # If a TAR archive was supplied, extract it and determine the path
    # to the patient directory
    if os.path.isfile(input_path) and tarfile.is_tarfile(input_path):

        tmp_dir = tempfile.mkdtemp()

        logger.info("Extracting TAR archive to: {0}".format(tmp_dir))

        t = tarfile.open(input_path)

        for m in t.getmembers():
            # Need to filter out files containing ":" for Windows
            if not ":" in m.name:
                t.extract(m, path=tmp_dir)

        input_path = tmp_dir

        # Walk directory with extracted archive, looking for directory
        # with Patient file
        pat_dirs = []
        for root, dirs, files in os.walk(input_path):

            if "Patient" in files:
                pat_dirs.append(root)

        if len(pat_dirs) == 0:
            logger.error(
                "No Pinnacle Patient directories were found in the "
                "supplied TAR archive"
            )
            exit()

        if len(pat_dirs) > 1:
            logger.error(
                "Multiple Pinnacle Patient directories were found in "
                "the supplied TAR archive"
            )
            logger.error(
                "The command line utility currently only support "
                "parsing TAR archives containing one patient"
            )
            exit()

        input_path = pat_dirs[0]

        logger.info("Using Patient directory: {0}".format(input_path))

    # Create Pinnacle object given input path
    p = PinnacleExport(input_path, logger)

    if list_available:
        logger.info("Plans and Trials:")
        p.log_trial_names()
        logger.info("Images:")
        p.log_images()
        exit()

    logger.info("Will export modalities: {0}".format(modality))

    # Check that the plan exists, if not select first plan
    plans = p.plans
    plan = None

    for pl in plans:
        if pl.plan_info["PlanName"] == plan_name:
            plan = pl

    if not plan:

        if plan_name:
            logger.error("Plan not found (" + plan_name + ")")
            exit()

        # Select a default plan if user didn't pass in a plan name
        plan = plans[0]
        logger.warning(
            "No plan name supplied, selecting first plan: {0}".format(
                plan.plan_info["PlanName"]
            )
        )

    # Set the Trial if it was given
    if trial:

        if not plan.set_active_trial(trial):
            logger.error(
                "No Trial: {0} found in Plan: {1}".format(
                    trial, plan.plan_info["PlanName"]
                )
            )
            exit()

    # If we got up to here, we are exporting something, so make sure the
    #  output_directory was specified
    if not output_directory:
        logger.error("Specifiy an output directory with -o")
        exit()

    if not os.path.exists(output_directory):
        logger.info("Creating output directory: " + output_directory)
        os.makedirs(output_directory)

    if uid_prefix:

        if not plan.is_prefix_valid(uid_prefix):
            logger.error("UID Prefix supplied is invalid")
            exit()
        plan.uid_prefix = uid_prefix

    primary_image_exported = False
    if image_series:

        image_series_uids = []

        if image_series == "all":
            for image in p.images:
                image_series_uids.append(image.image_header["series_UID"])
        else:
            image_series_uids.append(image_series)

        for suid in image_series_uids:
            logger.info("Exporting image with UID: {0}".format(suid))
            p.export_image(series_uid=suid, export_path=output_directory)

            series_uid = plan.primary_image.image_header["series_UID"]
            if plan.primary_image and series_uid == suid:
                primary_image_exported = True

    if "CT" in modality:

        if plan.primary_image:

            logger.info(
                "Exporting primary image for plan: {0}".format(
                    plan.plan_info["PlanName"]
                )
            )

            if primary_image_exported:
                logger.info("Primary image was already exported during this run")
            else:
                p.export_image(image=plan.primary_image, export_path=output_directory)
        else:
            logger.error(
                "No primary image to export for plan: {0}".format(
                    plan.plan_info["PlanName"]
                )
            )

    if "RTSTRUCT" in modality:
        p.export_struct(plan=plan, export_path=output_directory)

    if "RTPLAN" in modality:
        p.export_plan(plan=plan, export_path=output_directory)

    if "RTDOSE" in modality:
        p.export_dose(plan=plan, export_path=output_directory)
