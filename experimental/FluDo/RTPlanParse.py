import dicom as dcm
import os
import re


class RTPlanParser():
    ''' RTPlanParse class looks in source dcm file;
        checks to see what files start with RP and end in dcm;
        renames files that have 3 segments or more for
        IMRT candidates'''

    def __init__(self,parent=None):
        self.orig_dcm_path = None
        self.imrt_candidates = list()
        self.src_dcm_files = list()
        # need more than 3 segments on at least one beam to be IMRT
        self.cntrl_pt_thresh = 6
        self.getDCMFiles(r'D:\RTPlanFromPin')


    def getDCMFiles(self, root_dir):
        from os.path import join, getsize
        #files is a list
        os.chdir(root_dir)
        ptrn = re.compile(r'^RP.+\.(dcm$|DCM$)')
        i=0;

        for root, dirs, files in os.walk(root_dir):
            #print(i)
            i +=1
            for file in files:
                m = ptrn.match(file)
                if (m==None):
                    continue
                self.src_dcm_files.append(os.path.join(root, file))
        #print("I found this many files: %s" % len(self.src_dcm_files))

    def filterIMRT(self, my_src):
        # we assume my_src are valid dicom files
        for my_dcm in my_src:
            #print(my_dcm)
            ds = dcm.read_file(my_dcm)
            # arbitrarily look for beams with more than self.cntrl_pt_thresh control points
            # to be considered IMRT plans
            if any((cp.NumberOfControlPoints) > self.cntrl_pt_thresh for cp in ds.BeamSequence):
                tmp = str(ds.PatientName)
                pat_name = re.sub(r'[^a-zA-Z]', r'_', tmp)
                plan_name = str(ds.RTPlanName)
                plan_dt = str(ds.RTPlanDate)
                plan_tm = str(ds.RTPlanTime)
                self.imrt_candidates.append( (my_dcm, pat_name, plan_name, plan_dt, plan_tm) )
                new_fname = pat_name+str(plan_name)+'_'+str(plan_dt)+'_'+str(plan_tm)
                print(new_fname,"New filename")
                tmp2 = os.path.join(os.path.dirname(my_dcm), new_fname + '.dcm')
                if not os.path.exists(tmp2):
                    try:
                        os.rename(my_dcm, tmp2)
                    except:
                        print("Error renaming file from RTPlanParser")
        print ("I have %s IMRT candidates" % len(self.imrt_candidates))

