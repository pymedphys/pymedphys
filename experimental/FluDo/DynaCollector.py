# Copyright (C) 2018 Ben Cooper

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

 
import os
import re
import shutil
import csv

class StartHere():
    '''A Spot to run your main script.
    DynaCollator
    PURPOSE: traverse a given directory and collate DynaLog files (not recursive) into
    Patient folders, possibly with sub-folders for each fraction collected.
    This could be run once a day as a cron job (scheduled job).
    Used to try and facilitate the used of FluDo program.
    test

    AUTHOR:     B Cooper
    DATE:       2016-05-13
    Version:    0.5
    STATUS:     development - functional '''
    def __init__(self, choice=None):
        #my_path = 'D:\\Temp\\dyna_LA1'
        my_path = choice
        path_digest = DigestPath(my_path)#'/home/mpre/xxx/Dynalogs_from_2016-02-18')
        files_collated = CreateFolderStructure(path_digest.pat_log_records, my_path)

class DigestPath:
    def __init__(self, input_dir=None):
        assert (os.path.exists(input_dir) and (os.path.isdir(input_dir))), "check your directory %s exists ... I can't find it" % input_dir

        self.entries = os.listdir(input_dir)
        # pat_log_records dictionary has Aria patient number as
        # 'key' and a list of objects (pat_record) as the 'value'
        self.pat_log_records = dict()
        self.input_dir = input_dir
        self.do_work(self.input_dir, self.pat_log_records, self.entries)

    class pat_record:
        '''A class to act as a "struct" data container for
        meta data collected from the patient log files
        '''
        def __init__(self, last_name=None, first_name=None, pat_num=None,
                     uid=None, seq=None, log_date=None, log_time=None,
                     filename=None):
            self.pat_num = pat_num
            self.log_date = log_date
            self.log_time = log_time
            self.filename = filename
            self.last_name = last_name
            self.first_name = first_name
            self.pat_num_in = None
            self.uid = uid
            self.seq = seq


    def do_work(self, input_dir, pats, entries):


        for entry in entries:
            # use regular expression to pull out data from dynalog filename.
            # grp1: A or B carriage in MLC, gr2 is year, gr3 is month etc
            # grps 5, 6, 7 are hours, mins, seconds, grp 8 (after _ ) is Aria patient number
            ptrn = re.compile(r'(A|B)(\d\d\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)_(\d+)\.dlg')
            if os.path.isfile(os.path.join(input_dir, entry)):
                # print('Here is my entry: %s' % entry) #if os.path.isfile(entry)
                self.get_pat_log_record(input_dir, entry, pats, ptrn)

        for key, value in pats.items():
            print("Patient number: %s" % key)
            for entry in value:
                print('\t\tFilename is %s' % entry.filename)
                print('\t\t\t Logtime is %s' % entry.log_time)

    def get_pat_log_record(self, root_path, fname, pats, ptrn):
        m = ptrn.match(fname)
        if (m == None):
            #only continue if we get a complete match with dynalog filename
            return
        my_pat_rec = self.pat_record()

        #populate some fields of pat_record struct from matched groups
        my_pat_rec.pat_num = m.group(8)
        my_pat_rec.log_date = str(m.group(2)) + str(m.group(3)) + str(m.group(4))
        my_pat_rec.log_time = str(m.group(5)) + str(m.group(6)) + str(m.group(7))
        my_pat_rec.filename = os.path.join(root_path, fname)
        my_file = os.path.join(root_path, fname)

        #need to peek into file to get other fields of pat_record
        count=0
        with open(my_file, "r") as filehandle:
            while (count < 3):  #just read first 3 lines of dynalog file
                line = filehandle.readline()
                count +=1
                elems = (line.strip()).split(',')
                if count ==2:
                    #replace non-alphanumeric chars with _
                    tmp_str = elems[0]
                    my_pat_rec.last_name = re.sub(r'[^A-Za-z0-9_]+', '_', tmp_str)

                    #replace non-alphanumeric chars with _
                    tmp_str2 = elems[1]
                    my_pat_rec.first_name = re.sub(r'[^A-Za-z0-9_]+', '_', tmp_str2)
                    my_pat_rec.pat_num_in = elems[2]
                if count ==3:
                    my_pat_rec.uid = elems[0]
                    my_pat_rec.seq = elems[1]
                #my_lines.append(elems)

        my_list = list()
        patnum = my_pat_rec.pat_num

        if patnum in pats:
            pats[patnum].append(my_pat_rec)
        else:
            my_list.append(my_pat_rec)
            pats[patnum] = my_list

class CreateFolderStructure:
    def __init__(self, pat_records, container_path):
        assert os.path.isdir(container_path), "Container path must exist, can't find %s" % container_path
        self.pat_records = pat_records
        self.container_path = container_path
        self.do_work()

    def do_work(self):
        for k, v in (self.pat_records).items():
            for pat_rec in sorted(v, key=lambda x:x.filename):
                sub_folder = str(k)+"_"+pat_rec.last_name+"_"+pat_rec.first_name
                new_path = os.path.join(self.container_path, sub_folder, pat_rec.log_date)
                mystat = self.make_folders(new_path)
                if mystat == 0:
                    result = shutil.copy2(pat_rec.filename, new_path)
                    print ('file %s copied to %s' % (pat_rec.filename, result))

    def make_folders(self,pth):
        '''try and create folders in pth, including subfolders
        if they do not already exist.
        returns 0 on success or if already exists
        returns -1 on exception
        '''
        if not os.path.exists(pth):
            try:
                os.makedirs(pth)
                print("created %s" % pth)
                return 0
            except:
                print("%s not created" % pth)
                return -1
        return 0

