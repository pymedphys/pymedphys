# Copyright (C) 2018 Cancer Care Associates

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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""A GUI to assist in de-archiving patient files.
"""

import sys
from time import sleep

import search_and_move
from PyQt4 import QtCore, QtGui


class ProgressBarWorker(QtCore.QThread):
    """Thread for determining amount of data transfered.
    """

    percent = QtCore.pyqtSignal(object)

    def __init__(self, parent_thread, patient_id, origin_folder_size):
        super(ProgressBarWorker, self).__init__(parent_thread)
        self.patient_id = patient_id
        self.origin_folder_size = origin_folder_size

    def run(self):
        proportion = 0
        while proportion < 1:
            proportion = search_and_move.get_proportion_moved(
                self.patient_id, self.origin_folder_size
            )
            self.percent.emit(proportion * 100)
            sleep(1)


class DeArchiveWorker(QtCore.QThread):
    """Thread for completing the de-archive task.
    """

    error = QtCore.pyqtSignal(object)
    success = QtCore.pyqtSignal()

    def __init__(self, parent_thread, patient_id, patient_name):
        super(DeArchiveWorker, self).__init__(parent_thread)
        self.patient_id = patient_id
        self.patient_name = patient_name

    def run(self):
        try:
            search_and_move.dearchive_patient(self.patient_id, self.patient_name)

        except AssertionError as details:
            self.error.emit(details)

        else:
            self.success.emit()


class Example(QtGui.QWidget):
    def __init__(self):
        super(Example, self).__init__()

        self.initUI()

    def initUI(self):
        patient_id_label = QtGui.QLabel("Patient ID:")
        self.patient_id_edit = QtGui.QLineEdit()

        self.find_button = QtGui.QPushButton("Find Patient", self)
        self.find_button.clicked.connect(self.find_patient)

        patient_name_label = QtGui.QLabel("Patient Name:")
        self.patient_name_output = QtGui.QLabel("")

        self.dearchive_button = QtGui.QPushButton("De-Archive", self)
        self.dearchive_button.setEnabled(False)
        self.dearchive_button.clicked.connect(self.dearchive)

        self.progress_bar = QtGui.QProgressBar(self)

        grid = QtGui.QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(patient_id_label, 1, 0)
        grid.addWidget(self.patient_id_edit, 1, 1)

        grid.addWidget(self.find_button, 2, 0)

        grid.addWidget(patient_name_label, 3, 0)
        grid.addWidget(self.patient_name_output, 3, 1)

        grid.addWidget(self.dearchive_button, 4, 1)

        grid.addWidget(self.progress_bar, 5, 0, 1, 2)

        self.setLayout(grid)

        self.setGeometry(300, 300, 250, 150)
        self.setWindowTitle("De-Archive Patient")

        self.show()

    def find_patient(self):
        patient_id = self.patient_id_edit.text()
        try:
            patient_name = search_and_move.display_patient_name(patient_id)

        except AssertionError as details:
            self.error(details)

        else:
            self.patient_name_output.setText(patient_name)
            self.dearchive_button.setEnabled(True)

    def update_progress_bar(self, percent):
        self.progress_bar.setValue(percent)

    def run_progress_bar(self, patient_id):
        origin_folder_size = search_and_move.get_origin_folder_size(patient_id)
        progressbar_worker = ProgressBarWorker(self, patient_id, origin_folder_size)

        progressbar_worker.percent.connect(self.update_progress_bar)
        progressbar_worker.start()

    def dearchive(self):
        patient_id = self.patient_id_edit.text()
        patient_name = self.patient_name_output.text()

        try:
            search_and_move.check_patient_name(patient_id, patient_name)
            search_and_move.check_folders(patient_id)

            self.patient_id_edit.setEnabled(False)
            self.dearchive_button.setEnabled(False)
            self.find_button.setEnabled(False)

            self.run_progress_bar(patient_id)

            dearchive_worker = DeArchiveWorker(self, patient_id, patient_name)
            dearchive_worker.error.connect(self.error)
            dearchive_worker.success.connect(self.close)
            dearchive_worker.start()

        except AssertionError as details:
            self.error(details)

    def close(self):
        confirmation_message = QtGui.QMessageBox()
        confirmation_message.setText(
            "Patient has been successfully de-archived. Will now quit."
        )
        confirmation_message.setWindowTitle("Success")
        confirmation_message.addButton(QtGui.QMessageBox.Ok)
        confirmation_message.setDefaultButton(QtGui.QMessageBox.Ok)
        confirmation_message.exec_()

        QtGui.QApplication.quit()

    def error(self, details):
        print(details)
        error_message = QtGui.QMessageBox()
        error_message.setWindowTitle("Error")
        error_message.setText(str(details))
        error_message.addButton(QtGui.QMessageBox.Ok)
        error_message.exec_()


def main():

    app = QtGui.QApplication(sys.argv)
    ex = Example()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
