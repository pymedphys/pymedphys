import sys
import os
import logging

from .pinn_yaml import pinn_to_dict
from .pinnacle_plan import PinnaclePlan
from .pinnacle_image import PinnacleImage
from .rtstruct import convert_struct
from .rtplan import convert_plan
from .rtdose import convert_dose
from .image import convert_image


# This class holds all information relating to the Pinnacle Dataset
# Can be used to export various elements of the dataset, Images,
# RTSTRUCT, RTPLAN or RTDOSE.
class Pinnacle:

    logger = None  # Logger to use for all logging

    path = ""  # Path to the root directory of the dataset (containing
    # the Patient file)
    patient_info = None  # The patient data read from
    plans = None  # Pinnacle plans for this path
    images = None  # Images found in image.info

    def __init__(self, path, logger=None):

        self.path = path
        self.logger = logger

        if not self.logger:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.DEBUG)

            if len(self.logger.handlers) == 0:
                ch = logging.StreamHandler(sys.stdout)
                formatter = logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s')
                ch.setFormatter(formatter)
                ch.setLevel(logging.DEBUG)

                self.logger.addHandler(ch)

    def get_patient_info(self):

        if not self.patient_info:
            path_patient = os.path.join(self.path, "Patient")
            self.logger.debug(
                'Reading patient data from: {0}'.format(path_patient))
            self.patient_info = pinn_to_dict(path_patient)

            # Set the full patient name
            self.patient_info['FullName'] = "{0}^{1}^{2}^".format(
                self.patient_info['LastName'],
                self.patient_info['FirstName'],
                self.patient_info['MiddleName'])

            # gets birthday string with numbers and dashes
            dobstr = self.patient_info['DateOfBirth']
            if '-' in dobstr:
                dob_list = dobstr.split('-')
            elif '/' in dobstr:
                dob_list = dobstr.split('/')
            else:
                dob_list = dobstr.split(' ')

            dob = ""
            for num in dob_list:
                if len(num) == 1:
                    num = '0' + num
                dob = dob + num

            self.patient_info['DOB'] = dob

        return self.patient_info

    def get_plans(self):

        # Read patient info to populate patients plns
        if not self.plans:
            self.get_patient_info()

            self.plans = []
            for plan in self.patient_info['PlanList']:
                path_plan = os.path.join(
                    self.path, "Plan_"+str(plan['PlanID']))
                self.plans.append(PinnaclePlan(self, path_plan, plan))

        return self.plans

    def get_images(self):

        # Read patient info to populate patients images
        if not self.images:
            self.get_patient_info()

            self.images = []
            for image in self.patient_info['ImageSetList']:
                pi = PinnacleImage(self, self.path, image)
                self.images.append(pi)

        return self.images

    def export_struct(self, plan, export_path="."):

        # Export Structures for plan
        convert_struct(plan, export_path)

    def export_dose(self, plan, export_path="."):

        # Export dose for plan
        convert_dose(plan, export_path)

    def export_plan(self, plan, export_path="."):

        # Export rtplan for plan
        convert_plan(plan, export_path)

    def export_image(self, image=None, series_uid="", export_path="."):

        for im in self.get_images():
            im_info = im.get_image_info()[0]
            im_suid = im_info['SeriesUID']
            if len(series_uid) > 0 and im_suid == series_uid:
                convert_image(im, export_path)
                break

        if image:
            convert_image(image, export_path)

    def print_images(self):

        for i in self.get_images():
            image_header = i.get_image_header()
            self.logger.info('{0}: {1} {2}'.format(
                image_header['modality'],
                image_header['series_UID'],
                image_header['SeriesDateTime']))

    def print_plan_names(self):

        for p in self.get_plans():
            self.logger.info(p.plan_info['PlanName'])

    def print_trial_names(self):

        for p in self.get_plans():
            self.logger.info('### ' + p.plan_info['PlanName'] + ' ###')
            for t in p.get_trials():
                self.logger.info('- '+t['Name'])

    def print_trial_names_in_plan(self, p):

        self.logger.info('### ' + p.plan_info['PlanName'] + ' ###')
        self.logger.info(p.path)
        for t in p.get_trials():
            self.logger.info('- '+t['Name'])
