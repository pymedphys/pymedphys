import datetime
import os
import subprocess as sp
import sys

import dicom as dcm
import numpy as np
import pytictoc
from PyPDF2 import PdfFileReader, PdfFileMerger
from PyQt5 import QtCore, QtGui, QtWidgets, Qt
from matplotlib import colors
from matplotlib.backends.backend_pdf import PdfPages
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from scipy import interpolate as interpl
from scipy import stats as spstats

import DynaCollector
import PinRTPlanDCM as pdcm
import TimeDialogScript as TDScript
from Dyn_to_Dose import Dyn_to_Dose as d2d
from QAResultsForm import Ui_Dialog


class QAResultsDlg(QtWidgets.QDialog,Ui_Dialog):
    def __init__(self, parent=None):
        super(QAResultsDlg, self).__init__(parent)
        self.setupUi(self)
        self.DCMFile=None
        self.DynsPath=''
        self.DoseDiffs=[]
        self.PDFPath=''
        self.dateEdit_CurDate.setDateTime(QtCore.QDateTime.currentDateTime())
        self.dateTimeEdit_ApprovedBy.setDateTime(QtCore.QDateTime.currentDateTime())
        self.CurLinac=0
        self.ComboBox_RadCalcResults.valueChanged.connect(self.UpdateRadCalcTol)
        self.ComboBox_RadCalcTol.currentIndexChanged.connect(self.ChangeColorRadCalcTol)
        self.ComboBox_OKToStart.currentIndexChanged.connect(self.ChangeColorOKToStart)
        self.tableWidget.cellChanged.connect(self.ColorCells)
        self.pushButtonOK.clicked.connect(self.SaveWidgetAsTiff)
        self.pushButtonDeliveryDone.clicked.connect(self.AnalyseDynalogs)
        self.AllMUsMatch=0
        self.NumBeams=0
        self.Restart=1
        self.PowerShellPath=''
        self.CurDir=''



    def ColorCells(self):
        numRows=self.tableWidget.rowCount()
        for x in range(0,numRows,1):
            try:
                PlanMU=self.tableWidget.item(x,3).text()
                DeliveredMU=self.tableWidget.item(x,4).text()
                if(PlanMU==DeliveredMU):
                    self.tableWidget.item(x,5).setBackground(QtCore.Qt.green)
                    self.AllMUsMatch=1
                else:
                    self.tableWidget.item(x, 5).setBackground(QtCore.Qt.red)
                    self.AllMUsMatch=0
            except:
                pass
                #print("Error validating")

    def SaveWidgetScreenShot(self, Widget, filename):
        pixelMap =QtGui.QPixmap(Widget.size())
        Widget.render(pixelMap,Qt.QPoint(), Qt.QRegion())
        pixelMap.save(filename, quality=100)

    def SaveWidgetAsTiff(self):
        os.chdir(self.CurDir)
        #self.updateDoseDiff()
        self.SaveWidgetScreenShot(self,"Report.tiff")
        c = canvas.Canvas("Report.pdf", pagesize=A4)
        c.setFont('Times-Bold', 18)
        c.drawString(50, 805, "                                              Plan QA Report")
        c.line(50, 800, 550, 800)
        print(os.getcwd(),"Current working dir")
        c.drawImage("MPREBadge.PNG", 50, 690, width=500, height=100)
        c.drawImage("Report.tiff", 50, -20, width=500, height=900, preserveAspectRatio=True)
        c.save()
        merger = PdfFileMerger()
        merger.append(PdfFileReader(open("Report.pdf", "rb")))
        merger.append(PdfFileReader(open(self.PDFPath, "rb")))
        merger.write(self.PDFPath)
        os.startfile(self.PDFPath)
        self.close()

    def UpdateRadCalcTol(self):
        Value=np.float(self.ComboBox_RadCalcResults.text())
        if(Value<=3.0 and Value>=-3.0):
            self.ComboBox_RadCalcTol.setCurrentIndex(1)
        else:
            self.ComboBox_RadCalcTol.setCurrentIndex(2)

    def ChangeColorRadCalcTol(self):
        if self.ComboBox_RadCalcTol.currentIndex()==1:
            self.ComboBox_RadCalcTol.setStyleSheet("background-color: rgb(0, 255,0);")
        elif self.ComboBox_RadCalcTol.currentIndex()==2:
            self.ComboBox_RadCalcTol.setStyleSheet("background-color: rgb(255,0,0);")

    def ChangeColorOKToStart(self):
        if self.ComboBox_OKToStart.currentIndex()==1:
            self.ComboBox_OKToStart.setStyleSheet("background-color: rgb(0, 255,0);")
        elif self.ComboBox_OKToStart.currentIndex()==2:
            self.ComboBox_OKToStart.setStyleSheet("background-color: rgb(255,0,0);")

    def updateForm(self):
        data = dcm.read_file(self.DCMFile)
        PatID = data.PatientID
        self.PatID = PatID
        PatName = data.PatientName
        PatDOB = data.PatientBirthDate
        if PatDOB=='':
            PatDOB='XXXX-XX-XX'
        DOB1=list(PatDOB)
        PatDOB1=DOB1[0]+DOB1[1]+DOB1[2]+DOB1[3]+"-"+DOB1[4]+DOB1[5]+"-"+DOB1[6]+DOB1[7]
        PlanName = data.RTPlanName

        #update form with details
        self.lineEdit_PatID.setText(PatID)
        self.lineEdit_DOB.setText(str(PatDOB1))
        self.lineEdit_PatName.setText(str(PatName))
        self.lineEdit_PlanName.setText(str(PlanName))
        self.ComboBox_LA.setCurrentIndex(self.CurLinac)

        FGS = data.FractionGroupSequence[0].ReferencedBeamSequence
        BS = data.BeamSequence
        self.NumBeams=np.size(FGS)
        print(self.NumBeams)
        for x in range(0,self.NumBeams, 1):
            MU = FGS[x].BeamMeterset
            BeamName = BS[x].BeamName
            BeamNum = BS[x].BeamNumber
            BeamAngle = BS[x].ControlPointSequence[0].GantryAngle
            print(MU,BeamName,BeamNum,BeamAngle)
            self.tableWidget.setItem(x,0,QtWidgets.QTableWidgetItem(str(BeamNum)))
            self.tableWidget.setItem(x,1, QtWidgets.QTableWidgetItem(str(BeamName)))
            self.tableWidget.setItem(x,2, QtWidgets.QTableWidgetItem(str(BeamAngle)))
            self.tableWidget.setItem(x,3, QtWidgets.QTableWidgetItem(str(MU)))
            self.tableWidget.setItem(x,4, QtWidgets.QTableWidgetItem(str("")))
            self.tableWidget.setItem(x,5, QtWidgets.QTableWidgetItem(str("")))
            try:
                self.tableWidget.setItem(x,6, QtWidgets.QTableWidgetItem(str(self.DoseDiffs[x])))
            except:
                pass
            self.tableWidget.item(x, 0).setTextAlignment(4)
            self.tableWidget.item(x, 1).setTextAlignment(4)
            self.tableWidget.item(x, 2).setTextAlignment(4)
            self.tableWidget.item(x, 3).setTextAlignment(4)
            self.tableWidget.item(x, 4).setTextAlignment(4)
            try:
                self.tableWidget.item(x, 6).setTextAlignment(4)
            except:
                pass

    def updateDoseDiff(self):
        for x in range(0,self.NumBeams,1):
            print(x,'Num Of Beam')
            self.tableWidget.setItem(x,6,QtWidgets.QTableWidgetItem(str(self.DoseDiffs[x])))
            self.tableWidget.item(x,6).setTextAlignment(4)
            if self.DoseDiffs[x]<95.0:
                self.tableWidget.item(x,6).setBackground(QtCore.Qt.red)

    def jaw_match(self, pin, dyn, i, j):
        # tolerance to match jaw positions (mm)
        mytol = 2

        # convert dynalog jaw pos to integral mm and using DICOM co-ords
        d_y2 = int(10 * (dyn.my_logs[i].axis_data.jaws.y2.actual)[0])
        d_x2 = int(10 * (dyn.my_logs[i].axis_data.jaws.x2.actual)[0])
        d_y1 = int(-10 * (dyn.my_logs[i].axis_data.jaws.y1.actual)[0])
        d_x1 = int(-10 * (dyn.my_logs[i].axis_data.jaws.x1.actual)[0])

        difs = [abs(d_y2 - int(pin.y2jaw[j])),
                abs(d_x2 - int(pin.x2jaw[j])),
                abs(d_y1 - int(pin.y1jaw[j])),
                abs(d_x1 - int(pin.x1jaw[j]))]
        for d in difs:
            if d >= mytol:
                print('d is ', d)
                return False
        # fall throguh to here means all difs must be < mytol:
        return True

    def add_maps(self,src, norm, title, fig, ax):
        # add plots to a single figure
        im1 = ax.imshow(src, norm=norm,cmap='jet',interpolation='bicubic')
        ax.set_title(title)
        my_cax = fig.add_axes([0.92, 0.10, 0.02, 0.80])
        my_ticks = [15.0, 25.0, 50.0, (0.98 * np.max(src))]
        cbar = fig.colorbar(im1, cax=my_cax, ticks=my_ticks, label='arb. units')
        return fig, ax

    def add_histo(self, diffs, fig, ax, bins=20):
        ax.hist(diffs.flatten(), bins, color='green', alpha=0.8)
        ax.set_title('Histogram of % error (Pinnacle as reference)')
        ax.set_xlabel('Percent error')
        ax.set_ylabel('Counts')
        return fig, ax

    def AnalyseDynalogs(self):
        if self.Restart==1:
            # **************************Running Get_Dynalogs***************************************************************
            TimeDlg = TDScript.TimeDlg(self)
            TimeDlg.setModal(False)
            TimeDlg.exec_()

            TimeLimitDyn = TimeDlg.comboBoxTime.currentIndex()
            # SelectedLinac=self.ui.comboBoxLA.currentIndex()

            # QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            if TimeLimitDyn == 0:
                arg0 = "a"
            elif TimeLimitDyn == 1:
                arg0 = "b"
            elif TimeLimitDyn == 2:
                arg0 = "c"
            elif TimeLimitDyn == 3:
                arg0 = "d"

            # Add  m/c ID to args
            if self.CurLinac == 0:
                arg1 = "1"
            elif self.CurLinac == 1:
                arg1 = "3"
            elif self.CurLinac == 2:
                arg1 = "4"

            print(self.PowerShellPath,'#####################')
            #CopyDyns = sp.call(["C:\\WINDOWS\\system32\\WindowsPowerShell\\v1.0\\powershell.exe", '-ExecutionPolicy',
                                #'Unrestricted', '-WindowStyle', 'maximized', self.PowerShellPath, arg0, arg1])
            CopyDyns = sp.call(["C:\\WINDOWS\\system32\\WindowsPowerShell\\v1.0\\powershell.exe", '-ExecutionPolicy',
                                'Unrestricted','-WindowStyle','Normal',self.PowerShellPath, arg0, arg1])
            # QtGui.QApplication.restoreOverrideCursor()
            # ************************************End Get_Dynalogs*******************************************************

            # *************************************Running Parse_Dynalogs***********************************************
            # self.ui.statusbar.showMessage("Running Parse_Dynalog...")
            DC = DynaCollector
            la1_dyna_path = r'D:\Temp\dyna_La1'
            la3_dyna_path = r'D:\Temp\dyna_La3'
            la4_dyna_path = r'D:\Temp\dyna_La4'

            if (self.CurLinac == 0):
                x = DC.StartHere(la1_dyna_path)
            elif (self.CurLinac == 1):
                x = DC.StartHere(la3_dyna_path)
            elif (self.CurLinac == 2):
                x = DC.StartHere(la4_dyna_path)
                # self.ui.statusbar.showMessage("End of Parse_Dynalog")
                # *************************************************End Parse_Dynalogs****************************************

        init_dynalog_path=self.DynsPath
        pinnacle_dcm_path=self.DCMFile
        dynalog_dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Dynalog dir", init_dynalog_path)
        assert len(dynalog_dir_path) >= 1, len(pinnacle_dcm_path) >= 1

        # read in dynalog directory
        my_dyn2dose = d2d(dynalog_dir_path)

        # sort them according to attribute "filename".  This orders them by
        # time, oldest to newest by virtue of the file naming convention of
        # dynalogs
        my_dyn2dose.my_logs.sort(key=lambda x: x.filename)
        NumLogs=0
        for ml in my_dyn2dose.my_logs:
            hd, tail = os.path.split(ml.filename)
            NumLogs+=1
        LogsStr = "No. of logs found: "+str(NumLogs)

        self.textEditInfo.append(LogsStr)
        self.textEditInfo.append("*********************************************************************************")
        # calc and reconstruct fluence from Dynalogs
        my_dyn2dose.do_calcs(1.0)

        # ************************LaunchFluDO   CELL 02**************************************************************************
        my_od_maps = pdcm.PinRTPlanDCM(self.DCMFile)
        print(pinnacle_dcm_path,'RTPlan')
        flu_y = [-19.5, -18.5, -17.5, -16.5, -15.5, -14.5, -13.5, -12.5, -11.5, -10.5, -9.75,
                 -9.25, -8.75, -8.25, -7.75, -7.25, -6.75, -6.25, -5.75, -5.25, -4.75, -4.25,
                 -3.75, -3.25, -2.75, -2.25, -1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25,
                 1.75, 2.25, 2.75, 3.25, 3.75, 4.25, 4.75, 5.25, 5.75, 6.25, 6.75, 7.25, 7.75,
                 8.25, 8.75, 9.25, 9.75, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5,
                 19.5]
        flu_x = np.linspace(-19.95, 19.95, 400)

        print(my_dyn2dose.gant_angle)

        for i in range(0, len(my_dyn2dose.gant_angle)):
            Str1="Processing beam: "+str(i)
            self.textEditInfo.append(Str1)
            j = 0
            while True:
                tol = 1.5  # tolerance for gantry angles
                if abs(my_dyn2dose.gant_angle[i] - my_od_maps.gant_angles[j]) <= tol:
                    self.textEditInfo.append('potential match! j is {0:d} angle {1:f}'.format(j, my_od_maps.gant_angles[j]))
                    if self.jaw_match(my_od_maps, my_dyn2dose, i, j):
                        self.textEditInfo.append('got a match! j is {0:d} angle {1:f}'.format(j, my_od_maps.gant_angles[j]))
                        my_dyn2dose.od_map_index[i] =j
                        break
                    else:
                        self.textEditInfo.append('jaws do not agree - split beam perhaps?')

                        j += 1
                elif ((my_dyn2dose.gant_angle[i] < 0.8) or (my_dyn2dose.gant_angle[i] > 359.2)):
                    if ((my_od_maps.gant_angles[j] < 0.8) or (my_od_maps.gant_angles[j] > 359.2)):
                        self.textEditInfo.append('potential match near gant 0! j is {0:d} angle {1:f}'.format(j, my_od_maps.gant_angles[j]))
                        if self.jaw_match(my_od_maps, my_dyn2dose, i, j):
                            self.textEditInfo.append('got a match! j is {0:d} angle {1:f}'.format(j, my_od_maps.gant_angles[j]))
                            my_dyn2dose.od_map_index[i] = j
                            break
                        else:
                            self.textEditInfo.append('jaws do not agree - split beam perhaps?')
                            j += 1
                    else:
                        self.textEditInfo.append("need to increment j. j old is {0:d}".format(j))
                        j += 1
                elif j > my_od_maps.num_beams:
                    self.textEditInfo.append("j incremented out of range - didn't get a gantry angle match")
                    break
                else:
                    j += 1
        self.textEditInfo.append("*********************************************************************************")

        # Create the Pinnacle zoom list 'my_pin_zoom_list' which
        # zooms in on the Pinnacle map according to jaws (y jaws - 1.0 cm)
        # pre-allocate the list

        my_pin_zoom_list =[None]*my_dyn2dose.num_logs
        for i in range(0, my_dyn2dose.num_logs):
            print(i)
            y2 = (my_dyn2dose.my_logs[i].axis_data.jaws.y2.actual)[0]
            x2 = (my_dyn2dose.my_logs[i].axis_data.jaws.x2.actual)[0]
            y1 = (my_dyn2dose.my_logs[i].axis_data.jaws.y1.actual)[0]
            x1 = (my_dyn2dose.my_logs[i].axis_data.jaws.x1.actual)[0]

            rows = np.linspace(-1.0 * (y1 - 0.05), (y2 - 0.05), ((y2 + y1) * 10))
            cols = np.linspace(-1.0 * (x1 - 0.05), (x2 - 0.05), ((x1 + x2) * 10))

            indx = my_dyn2dose.od_map_index[i]
            # some code to crop our fludo arrays to the same size as pin_zoom
            dm = my_od_maps.flus[indx]
            my_tmp = interpl.RectBivariateSpline(flu_x, flu_x, dm, kx=1, ky=1, s=0)
            my_pin_zoom_list[i] = my_tmp(rows, cols)

            my_dyn2dose.make_interp_single(i, rows, cols)

        # plot some fluences and dose maps TODO: Save 1 A4 page per beam.
        my_fig = 0

        #************************LaunchFluDO   CELL 03******************************************************************
        print(my_dyn2dose.gant_angle)
        Str2="Gantry angles found: "+str(my_dyn2dose.gant_angle)
        self.textEditInfo.append(Str2)
        self.textEditInfo.append("*********************************************************************************")

        #************************LaunchFluDO   CELL 04******************************************************************
        right_now = datetime.datetime.now()

        # get some demographics from Pinnacle Patient
        my_pin_dcm = my_od_maps.ds
        tt = str(my_pin_dcm.PatientName).split("^")
        plan_dt = str(my_pin_dcm.RTPlanDate)
        plan_nm = str(my_pin_dcm.RTPlanName)
        ts = tt[0].upper() + ", " + tt[1]

        # folder path to store PDFs
        pdf_dir = r'D:\FluDo_PDF'
        fname = tt[0].upper() + "-" + tt[1] + "_" + (right_now.strftime("%Y%m%d-%H%M%S")) + ".pdf"
        self.PDFPath = os.path.join(pdf_dir, fname)
        self.textEditInfo.append("PDF will be saved to :"+self.PDFPath)
        print(self.PDFPath,'PDF')

        pp = PdfPages(self.PDFPath)
        import matplotlib.pyplot as plt

        #QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        for i in range(0, my_dyn2dose.num_logs):
            f, axarray =plt.subplots(2, 2)

            my_pin_zoom = 100 * my_pin_zoom_list[i]
            pin_indx = my_dyn2dose.od_map_index[i]

            if hasattr (my_pin_dcm.BeamSequence[pin_indx],'BeamDescription'):
                beam_name = str(my_pin_dcm.BeamSequence[pin_indx].BeamDescription)
            else:
                beam_name = "angle {0}".format(my_dyn2dose.gant_angle[i])

            my_pin_amax = np.unravel_index(my_pin_zoom.argmax(), my_pin_zoom.shape)

            print("pinnacle amax index: ")
            print(my_pin_amax)

            # max_fludo = np.max(my_dyn2dose.interp_fluences[i])
            # my_FluDo = 100*(1/max_fludo)*my_dyn2dose.interp_fluences[i]
            my_FluDo = 100.0 * my_dyn2dose.interp_fluences[i]
            my_fd_amax = np.unravel_index(my_FluDo.argmax(), my_FluDo.shape)

            print("FluDo amax index: ")
            print(my_fd_amax)

            # create the colors.Normalize object (matplotlib)
            my_norm = colors.Normalize(vmin=np.min(my_pin_zoom),
                                       vmax=1.05 * np.max(my_pin_zoom), clip=True)

            # create Pinnacle Dose map
            # show_maps(my_pin_zoom, my_norm, 'Pinn Dose Map')
            f1, ax1 =self.add_maps(my_pin_zoom, my_norm, 'Planned Beam', f, axarray[0, 1])

            # stuff = input("Can you see 'Pinn Dose Map' figure?")

            # DO the 1st gaussian convolution on fluence
            # blur = ndi.filters.gaussian_filter(my_FluDo, 3.2, order=0, mode='reflect',
            #                                    cval=0.00, truncate=6.0)
            blur = my_FluDo
            my_diff_pct = 100.0*abs((blur - my_pin_zoom) / np.max(my_pin_zoom))
            ##my_diff_pct = 100*abs((blur - my_pin_zoom)/ np.max(blur))

            my_mode, my_count = spstats.mode(my_diff_pct, axis=0)
            max_mode_diff = np.max(my_mode)

            print('maximum modal diff: %6.3f' % max_mode_diff)
            f2, ax2 =self.add_maps((blur), my_norm, 'Delivered Dynalog Beam', f, axarray[1, 1])
            print(np.shape(my_pin_zoom), ":Pin zoom OD shape")
            print(np.shape(blur), ":Dynalog OD shape")

            # For now, simply find the modal difference and add it on to the
            # FluDo map
            my_diff_dc = 100 * abs((blur - my_pin_zoom) / np.max(my_pin_zoom))
            ##my_diff_dc = 100*abs((blur - my_pin_zoom)/np.max(blur))

            dat = ((0.01 * my_diff_dc) * my_pin_zoom)
            # display_histo(dat)
            f3, ax3 =self.add_histo(dat, f, axarray[0, 0], 20)

            f4, ax4 =self.add_maps(0.01 * my_diff_pct * my_pin_zoom, my_norm, 'Difference Map', f, axarray[1, 0])

            hist, edges = np.histogram(dat, bins=40)
            print('{0}'.format(hist))
            print('{0}'.format(edges[0:15]))

            total = np.sum(hist)
            print("total is {0:d}".format(total))
            targ = 0
            targ2 = 0
            delta = 1.01
            delta2 = 3.01
            # BJC added 2017-04-04
            if edges[-1] < delta:
                targ =len(edges) -2
                targ2 = len(edges) -2
            else:
                for edge in edges:
                    if edge < delta:
                        targ += 1
                    if edge < delta2:
                        targ2 += 1


            my_fails = np.sum(hist[targ:-1])
            my_pct_pass = 1 - (my_fails / total)

            my_fails2 = np.sum(hist[targ2: -1])
            my_pct_pass2 = 1 - (my_fails2 / total)

            ax4 = axarray[1, 0]
            plt.setp(ax4.get_xticklabels(), visible=False)
            plt.setp(ax4.get_yticklabels(), visible=False)
            ax4.yaxis.set_ticks([])
            ax4.xaxis.set_ticks([])

            ax3.text(0.28, 0.90,
                     ("percentage of pixels < {0:d} % error is {1:.1f}".format(int(delta), 100 * my_pct_pass)),
                     horizontalalignment='left', transform=ax3.transAxes, fontsize=14)
            ax3.text(0.28, 0.83,
                     ("percentage of pixels < {0:d} % error is {1:.1f}".format(int(delta2), 100 * my_pct_pass2)),
                     horizontalalignment='left', transform=ax3.transAxes, fontsize=14)
            ax3.text(0.28, 0.76, ("Beam angle is: {0:.1f}".format(my_dyn2dose.gant_angle[i])),
                     horizontalalignment='left', transform=ax3.transAxes, fontsize=14)
            print(ts)

            f.suptitle('IMRT QA report for patient: {0:s}\nBeam Label: {1:s} | Plan Date: {2:s} | Plan Name: {3:s}\n'
                       .format(ts, beam_name, plan_dt, plan_nm), fontsize=16)

            #plt.show()
            plt.savefig(pp, format='pdf')
            print("targ is: ", targ)
            print("hist[targ] is: ", hist[targ])
            print("pct pass is {0:f}".format(my_pct_pass))
            self.DoseDiffs.append(np.round((my_pct_pass2*100.0),1))
        pp.close()
        self.updateDoseDiff()
        self.ComboBox_OKToStart.setEnabled(True)
        self.pushButtonDeliveryDone.setEnabled(False)
        #QtGui.QApplication.restoreOverrideCursor()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    myapp = QAResultsDlg()
    myapp.show()
    myapp.setWindowTitle('QA Results')
    myapp.setStyle(QtWidgets.QStyleFactory.create('Plastique'))
    sys.exit(app.exec_())
