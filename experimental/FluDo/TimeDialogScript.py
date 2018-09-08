import sys

from PyQt5 import QtGui, QtWidgets

from TimeDialog import Ui_TimeDialog


class TimeDlg(QtWidgets.QDialog,Ui_TimeDialog):
    def __init__(self, parent=None):
        super(TimeDlg, self).__init__(parent)
        self.setupUi(self)

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    myapp = TimeDlg()
    myapp.show()
    sys.exit(app.exec_())