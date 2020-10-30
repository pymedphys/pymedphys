# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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

        logger.info("Extracting TAR archive to: %s", tmp_dir)

        t = tarfile.open(input_path)

        for m in t.getmembers():
            # Need to filter out files containing ":" for Windows
            if not ":" in m.name:
                t.extract(m, path=tmp_dir)

        input_path = tmp_dir

        # Walk directory with extracted archive, looking for directory
        # with Patient file
        pat_dirs = []
        for root, _, files in os.walk(input_path):

            if "Patient" in files:
                pat_dirs.append(root)

        if len(pat_dirs) == 0:
            logger.error(
                "No Pinnacle Patient directories were found in the "
                "supplied TAR archive"
            )
            sys.exit()

        if len(pat_dirs) > 1:
            logger.error(
                "Multiple Pinnacle Patient directories were found in "
                "the supplied TAR archive"
            )
            logger.error(
                "The command line utility currently only support "
                "parsing TAR archives containing one patient"
            )
            sys.exit()

        input_path = pat_dirs[0]

        logger.info("Using Patient directory: %s", input_path)

    # Create Pinnacle object given input path
    p = PinnacleExport(input_path, logger)

    if list_available:
        logger.info("Plans and Trials:")
        p.log_trial_names()
        logger.info("Images:")
        p.log_images()
        sys.exit()

    logger.info("Will export modalities: %s", modality)

    # Check that the plan exists, if not select first plan
    plans = p.plans
    plan = None

    for pl in plans:
        if pl.plan_info["PlanName"] == plan_name:
            plan = pl

    if not plan:

        if plan_name:
            logger.error("Plan not found (%s)", plan_name)
            sys.exit()

        # Select a default plan if user didn't pass in a plan name
        plan = plans[0]
        logger.warning(
            "No plan name supplied, selecting first plan: %s",
            plan.plan_info["PlanName"],
        )

    # Set the Trial if it was given
    if trial:

        try:
            plan.active_trial = trial
        except KeyError:
            logger.error(
                "No Trial: %s found in Plan: %s", trial, plan.plan_info["PlanName"]
            )
            sys.exit()

    # If we got up to here, we are exporting something, so make sure the
    #  output_directory was specified
    if not output_directory:
        logger.error("Specifiy an output directory with -o")
        sys.exit()

    if not os.path.exists(output_directory):
        logger.info("Creating output directory: %s", output_directory)
        os.makedirs(output_directory)

    if uid_prefix:

        if not plan.is_prefix_valid(uid_prefix):
            logger.error("UID Prefix supplied is invalid")
            sys.exit()
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
            logger.info("Exporting image with UID: %s", suid)
            p.export_image(series_uid=suid, export_path=output_directory)

            series_uid = plan.primary_image.image_header["series_UID"]
            if plan.primary_image and series_uid == suid:
                primary_image_exported = True

    if "CT" in modality:

        if plan.primary_image:

            logger.info(
                "Exporting primary image for plan: %s", plan.plan_info["PlanName"]
            )

            if primary_image_exported:
                logger.info("Primary image was already exported during this run")
            else:
                p.export_image(image=plan.primary_image, export_path=output_directory)
        else:
            logger.error(
                "No primary image to export for plan: %s", plan.plan_info["PlanName"]
            )

    if "RTSTRUCT" in modality:
        p.export_struct(plan=plan, export_path=output_directory)

    if "RTPLAN" in modality:
        p.export_plan(plan=plan, export_path=output_directory)

    if "RTDOSE" in modality:
        p.export_dose(plan=plan, export_path=output_directory)
