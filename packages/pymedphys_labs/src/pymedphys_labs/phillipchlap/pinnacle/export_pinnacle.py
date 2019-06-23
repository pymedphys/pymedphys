#!/usr/bin/env python

import sys
import os
import logging
import tarfile
import tempfile
import click

from .pinnacle import Pinnacle

sys.path.append('.')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@click.command()
@click.option('--output_directory', '-o', required=False, help="Directory in which to generate DICOM objects")
@click.option('--verbose', '-v', default=False, is_flag=True, help="Flag to output debug information")
@click.option(
    '--modality',
    '-m',
    multiple=True,
    required=False,
    default=["CT", "RTSTRUCT", "RTDOSE", "RTPLAN"],
    help="Modalities to export (CT exports the plans primary planning CT).",
    type=click.Choice(['CT', 'RTSTRUCT', 'RTPLAN', 'RTDOSE']))
@click.option('--plan', '-p', 'plan_name', help="The name of the plan to export (first plan will be exported by default)")
@click.option('--trial', '-t', help="The name of the trial to export (first trial will be exported by default)")
@click.option('--list', '-l', 'list_available', is_flag=True, help="List all plans and trials available")
@click.option('--image', '-i', 'image_series', help="The UID of an image series you would like to export (or 'all' to export all images)")
@click.option('--uid_prefix', help="Prefix to use for generated UIDs")
@click.argument('input_path')
def export(output_directory, verbose, modality, plan_name, trial, list_available, image_series, uid_prefix, input_path):
    """
    pinntardicom

    This package generates Dicom objects from raw Pinnacle Treatment Planning System data.

    Provide INPUT path to patient folder (containing the 'Patient' file) or a TAR archive.

    Caution: This package is intended for research purposes only and should not be used clinically!
    """

    # Set logger output level
    logger.remove()
    log_level = "INFO"
    if verbose:
        log_level = "DEBUG"
    logger.add(sys.stdout, level=log_level)

    # If a TAR archive was supplied, extract it and determine the path to the patient directory
    if os.path.isfile(input_path) and tarfile.is_tarfile(input_path):

        tmp_dir = tempfile.mkdtemp()

        logger.info("Extracting TAR archive to: {0}".format(tmp_dir))

        t = tarfile.open(input_path)

        for m in t.getmembers():
            if not ':' in m.name:  # Need to filter out files containing ':' for Windows
                t.extract(m, path=tmp_dir)

        input_path = tmp_dir

        # Walk directory with extracted archive, looking for directory with Patient file
        pat_dirs = []
        for root, dirs, files in os.walk(input_path):

            if 'Patient' in files:
                pat_dirs.append(root)

        if len(pat_dirs) == 0:
            logger.error(
                'No Pinnacle Patient directories were found in the supplied TAR archive')
            exit()

        if len(pat_dirs) > 1:
            logger.error(
                'Multiple Pinnacle Patient directories were found in the supplied TAR archive')
            logger.error(
                'The command line utility currently only support parsing TAR archives containing one patient')
            exit()

        input_path = pat_dirs[0]

        logger.info('Using Patient directory: {0}'.format(input_path))

    # Create Pinnacle object given input path
    p = Pinnacle(input_path, logger)

    if list_available:
        logger.info('Plans and Trials:')
        p.print_trial_names()
        logger.info('Images:')
        p.print_images()
        exit()

    logger.info('Will export modalities: {0}'.format(modality))

    # Check that the plan exists, if not select first plan
    plans = p.get_plans()
    plan = None

    for pl in plans:
        if pl.plan_info['PlanName'] == plan_name:
            plan = pl

    if not plan:

        if plan_name:
            logger.error('Plan not found ('+plan_name+')')
            exit()

        # Select a default plan if user didn't pass in a plan name
        plan = plans[0]
        logger.warning(
            'No plan name supplied, selecting first plan: ' + plan.plan_info['PlanName'])

    # Set the Trial if it was given
    if trial:

        if not plan.set_active_trial(trial):
            logger.error('No Trial: {0} found in Plan: {1}'.format(
                trial, plan.plan_info['PlanName']))
            exit()

    # If we got up to here, we are exporting something, so make sure the output_directory was specified
    if not output_directory:
        logger.error('Specifiy an output directory with -o')
        exit()

    if not os.path.exists(output_directory):
        logger.info('Creating output directory: ' + output_directory)
        os.makedirs(output_directory)

    if uid_prefix:

        if not plan.is_prefix_valid(uid_prefix):
            logger.error('UID Prefix supplied is invalid')
            exit()
        plan.uid_prefix = uid_prefix

    primary_image_exported = False
    if image_series:

        image_series_uids = []

        if image_series == 'all':
            for image in p.get_images():
                image_series_uids.append(
                    image.get_image_header()['series_UID'])
        else:
            image_series_uids.append(image_series)

        for suid in image_series_uids:
            logger.info('Exporting image with UID: {0}'.format(suid))
            p.export_image(series_uid=suid, export_path=output_directory)

            if plan.primary_image and plan.primary_image.get_image_header()['series_UID'] == suid:
                primary_image_exported = True

    if 'CT' in modality:

        if plan.primary_image:

            logger.info('Exporting primary image for plan: ' +
                        plan.plan_info['PlanName'])

            if primary_image_exported:
                logger.info(
                    'Primary image was already exported during this run')
            else:
                p.export_image(image=plan.primary_image,
                               export_path=output_directory)
        else:
            logger.error('No primary image to export for plan: ' +
                         plan.plan_info['PlanName'])

    if 'RTSTRUCT' in modality:
        p.export_struct(plan=plan, export_path=output_directory)

    if 'RTPLAN' in modality:
        p.export_plan(plan=plan, export_path=output_directory)

    if 'RTDOSE' in modality:
        p.export_dose(plan=plan, export_path=output_directory)


def main():

    # For setup console_scripts
    export()  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":

    export()  # pylint: disable=no-value-for-parameter
