# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'TimeDialog.ui'
#
# Created by: PyQt5 UI code generator 5.6
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_TimeDialog(object):
    def setupUi(self, TimeDialog):
        TimeDialog.setObjectName("TimeDialog")
        TimeDialog.resize(346, 43)
        TimeDialog.setModal(True)
        self.gridLayout = QtWidgets.QGridLayout(TimeDialog)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QtWidgets.QLabel(TimeDialog)
        font = QtGui.QFont()
        font.setPointSize(10)
        self.label.setFont(font)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.comboBoxTime = QtWidgets.QComboBox(TimeDialog)
        font = QtGui.QFont()
        font.setBold(False)
        font.setWeight(50)
        self.comboBoxTime.setFont(font)
        self.comboBoxTime.setObjectName("comboBoxTime")
        self.comboBoxTime.addItem("")
        self.comboBoxTime.addItem("")
        self.comboBoxTime.addItem("")
        self.comboBoxTime.addItem("")
        self.horizontalLayout.addWidget(self.comboBoxTime)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 1)

        self.retranslateUi(TimeDialog)
        QtCore.QMetaObject.connectSlotsByName(TimeDialog)

    def retranslateUi(self, TimeDialog):
        _translate = QtCore.QCoreApplication.translate
        TimeDialog.setWindowTitle(_translate("TimeDialog", "Time limit dialog"))
        self.label.setText(_translate("TimeDialog", "How old Dynalogs should be scanned?"))
        self.comboBoxTime.setItemText(0, _translate("TimeDialog", "10 mins ago"))
        self.comboBoxTime.setItemText(1, _translate("TimeDialog", "30 mins ago"))
        self.comboBoxTime.setItemText(2, _translate("TimeDialog", "3 hrs ago"))
        self.comboBoxTime.setItemText(3, _translate("TimeDialog", "1 day ago"))

