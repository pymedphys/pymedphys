# Copyright (C) 2018 Paul King

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

import numpy as np

from pymedphys.devices import write_prs

DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../data/devices/profiler")


def test_write_prs():

    x_prof = [(-50.0, 0), (-4.99, 0), (-5.01, 1),
              (4.99, 1), (5.01, 0), (50.0, 0)]
    y_prof = [(-50.0, 0), (-4.99, 0), (-5.01, 1),
              (4.99, 1), (5.01, 0), (50.0, 0)]

    # print(write_prs(x_prof, y_prof, None))

    file_name = os.path.join(DATA_DIRECTORY, 'test_varian_open.prs')
    with open(file_name) as test:
        contents = test.readlines()
    print(contents)

    # file_name = os.path.join(DATA_DIRECTORY, 'test_varian_open.prs')
    # assert np.allclose(write_prs(file_name).cax, 45.50562901780488)
    # assert np.allclose(write_prs(file_name).x[0][1], 0.579460838649598)
    # assert np.allclose(write_prs(file_name).y[0][1], 0.2910764234184594)

    # file_name = os.path.join(DATA_DIRECTORY, 'test_varian_wedge.prs')
    # assert np.allclose(write_prs(file_name).cax, 21.863167869662274)
    # assert np.allclose(write_prs(file_name).x[0][1], 0.5626051581458927)
    # assert np.allclose(write_prs(file_name).y[0][1], 0.260042064635505)

    # file_name = os.path.join(DATA_DIRECTORY, 'test_tomo_50mm.prs')
    # assert np.allclose(write_prs(file_name).cax, 784.320114110518)
    # assert np.allclose(write_prs(file_name).x[0][1], 563.4064789252321)
    # assert np.allclose(write_prs(file_name).y[0][1], 1.8690221773721463)


test_file = ['Version:\t 7\n',
             'Filename:\tC:\\SNC\\Profiler2\\X04D04.prs\n',
             'Date:\t 11/10/2018\t Time:\t16:56:28\n',
             'Description:\t\n',
             'Institution:\t\n',
             'Calibration File:\tC:\\SNC\\Profiler2\\Factors\\0000000\\X04.cal\n',
             '\tProfiler Setup\n', '\n', 'Collector Model:\tProfiler2\n',
             'Collector Serial:\t4736338 Revision:\tC\n',
             'Firmware Version:\t1.2.1\n', 'Software Version:\t1.1.0.0\n',
             'Buildup:\t0\tcm\tWaterEquiv\n',
             'Nominal Gain\t1\n',
             'Orientation:\tSagittal\n',
             'SSD:\t100\tcm\n',
             'Beam Mode:\tPulsed\n',
             'Tray Mount:\tNo\n',
             'Alignment:\tNone\n',
             'Collection Interval:\t50\n',
             '\n',
             '\tMachine Data\n',
             'Room:\t\n',
             'Machine Type:\t\n',
             'Machine Model:\t\n',
             'Machine Serial Number:\t\n',
             'Beam Type:\tElectron\tEnergy:\t0 MeV\n',
             'Collimator:\tLeft: 0 Right: 0 Top: 0 Bottom: 0 cm\n',
             'Wedge:\tNone\tat\t0\n', 'Rate:\t0\tmu/Min\tDose:\t0\n',
             'Gantry Angle:\t0 deg\tCollimator Angle:\t0 deg\n',
             '\n',
             '\tData Flags\n',
             'Background Used:\ttrue\n',
             'Pulse Mode:\ttrue\n',
             'Analyze Panels:\t1015679\n',
             '\n',
             '\tHardware Data\n',
             'Cal-Serial Number:\t4736338\n',
             'Cal-Revision:\tC\n',
             'Temperature:\t-98.96726775\n',
             'Dose Calibration\n',
             'Dose Per Count:\t0.0001214447548\n',
             'Dose:\t75.40000153\n',
             'Absolute Calibration:\tfalse\n',
             'Energy:\t4 MV\n',
             'TimeStamp:\t3/16/2008 11:35:0\n',
             'Comments:\t\n',
             'Gain Ratios for Amp0:\t\t1\t2\t4\t8\n',
             'Gain Ratios for Amp1:\t\t1\t2\t4\t8\n',
             'Gain Ratios for Amp2:\t\t1\t2\t4\t8\n',
             'Gain Ratios for Amp3:\t\t1\t2\t4\t8\n',
             '\n', 'Multi Frame:\tfalse\n',
             '# updates:\t25\n',
             'Total Pulses:\t3939\n',
             'Total Time:\t12.151773\n',
             'Detectors:\t83\t57\t0\t4\n',
             'Detector Spacing:\t0.4\n',
             'Concatenation:\tfalse\n',
             'TYPE\tUPDATE#\tTIMETIC\tPULSES\tERRORS\tX1\tX2\tX3\tX4\tX5\tX6\tX7\tX8\tX9\tX10\tX11\tX12\tX13\tX14\tX15\tX16\tX17\tX18\tX19\tX20\tX21\tX22\tX23\tX24\tX25\tX26\tX27\tX28\tX29\tX30\tX31\tX32\tX33\tX34\tX35\tX36\tX37\tX38\tX39\tX40\tX41\tX42\tX43\tX44\tX45\tX46\tX47\tX48\tX49\tX50\tX51\tX52\tX53\tX54\tX55\tX56\tX57\tY1\tY2\tY3\tY4\tY5\tY6\tY7\tY8\tY9\tY10\tY11\tY12\tY13\tY14\tY15\tY16\tY17\tY18\tY19\tY20\tY21\tY22\tY23\tY24\tY25\tY26\tY27\tY28\tY29\tY30\tY31\tY32\tY33\tY34\tY35\tY36\tY37\tY38\tY39\tY40\tY41\tY42\tY43\tY44\tY45\tY46\tY47\tY48\tY49\tY50\tY51\tY52\tY53\tY54\tY55\tY56\tY57\tY58\tY59\tY60\tY61\tY62\tY63\tY64\tY65\tY66\tY67\tY68\tY69\tY70\tY71\tY72\tY73\tY74\tY75\tY76\tY77\tY78\tY79\tY80\tY81\tY82\tY83\tZ0\tZ1\tZ2\tZ3\n',
             'BIAS1\t\t61200570\t\t\t-1.191165376e-05\t-1.725474125e-05\t8.120839397e-06\t-1.931354561e-05\t-2.081679958e-05\t-3.970551255e-06\t4.738517958e-07\t-5.261388905e-06\t-4.019570406e-06\t-1.274497934e-06\t-3.006507946e-06\t-3.03918738e-06\t-1.307177368e-07\t-5.196030037e-06\t-4.519565749e-05\t3.066964899e-05\t-8.627370627e-06\t-1.017964375e-05\t-9.199260726e-06\t-2.22710344e-05\t4.78753711e-06\t-1.08985913e-05\t-1.517959718e-05\t-3.664998545e-05\t-3.091474475e-05\t-2.168280459e-05\t-1.15685197e-05\t-5.17969032e-06\t-2.503244659e-05\t-2.728732755e-05\t-1.124172536e-05\t-2.679713604e-05\t-3.218924268e-06\t-1.782663135e-05\t-3.954211538e-05\t-3.006507946e-06\t1.753251645e-05\t1.702598522e-05\t1.983641656e-05\t7.352872694e-07\t-3.372517609e-05\t-1.601292276e-06\t-1.650311427e-06\t-3.267943419e-07\t-4.983613715e-06\t-1.506521916e-05\t-2.009785203e-06\t-4.803876827e-06\t-1.431359218e-05\t-2.763046161e-05\t-1.058813668e-05\t-1.790832994e-05\t7.026078352e-07\t-1.370902264e-05\t-1.535933407e-05\t-4.133948426e-06\t1.669919087e-05\t1.795734909e-05\t1.63397171e-07\t-8.365935154e-06\t-9.869189127e-06\t-2.233639327e-05\t-2.019589033e-05\t4.852895978e-06\t7.745025904e-06\t-4.493422202e-06\t2.941149078e-07\t-1.457502765e-05\t-1.37580418e-05\t-1.370902264e-05\t7.679667036e-07\t-3.800618197e-05\t4.852895978e-06\t1.645409512e-05\t-8.365935154e-06\t-1.449332907e-05\t3.74669713e-05\t-5.588183247e-06\t-1.513057803e-05\t-6.19275278e-06\t6.209092497e-07\t-8.153518832e-06\t-7.82672449e-06\t-5.735240701e-06\t1.732010012e-06\t3.218924268e-06\t-3.856173235e-06\t-9.754811107e-06\t-6.944379766e-06\t-1.06044764e-05\t-8.153518832e-06\t-7.630647884e-06\t-2.076778043e-05\t-9.787490541e-06\t1.715670295e-06\t-3.027749578e-05\t-4.754857675e-06\t1.369268293e-05\t-2.503244659e-05\t-5.751580418e-06\t1.862727749e-05\t4.918254846e-06\t-1.083323244e-05\t-1.482012341e-05\t-8.872466384e-06\t1.225478782e-05\t-2.080045986e-05\t-3.467287968e-05\t4.428063333e-06\t-9.869189127e-06\t-4.238522615e-05\t-1.486914256e-06\t-1.004892601e-05\t-1.217308924e-05\t-9.754811107e-06\t3.905192386e-06\t-2.352919262e-06\t5.392106642e-07\t6.372489668e-07\t5.831645032e-05\t1.588220502e-05\t-1.236916584e-05\t-6.127393912e-06\t-2.292462309e-05\t-1.939524419e-05\t1.682990861e-06\t-3.633953082e-05\t-4.220548926e-05\t-1.514691775e-05\t0\t9.362657897e-06\t4.607800221e-06\t-1.307177368e-07\t-6.911700332e-06\t6.454188253e-06\t-4.428063333e-06\t-9.052203272e-06\t-6.911700332e-06\t-1.042473951e-05\t-2.218933582e-05\t-4.150288143e-06\t1.483646312e-05\t-4.901915129e-08\t1.312079283e-05\n',
             'Calibration\t\t\t\t\t1.028096214\t1.061408779\t0.9965973116\t1.055272614\t1.078146853\t1.002129693\t1.096501372\t1.050381167\t1.054358569\t1.093069459\t1.106021174\t1.09880917\t1.032408969\t1.049693908\t1.062365347\t1.067116654\t1.040085553\t1.068092758\t1.046008828\t1.080694093\t1.077482732\t1.105229069\t1.024946821\t1.081409611\t1.067757574\t1.044029252\t1.0252669\t1.020575207\t1.000003471\t1.010830789\t1.076047657\t1.050299117\t1.087320248\t1.059079884\t1.034988099\t1.076017582\t1.077560406\t1.068087189\t1.043256484\t1.102561367\t1.070489574\t1.009546713\t1.005984465\t1.033921115\t1.004908552\t1.111951268\t1.029909196\t1.0112984\t1.043731043\t1.056627893\t1.052120862\t1.061566342\t1.057999906\t1.070989934\t0.9943316488\t1.052874204\t1.060810734\t1.064762562\t1.02553437\t1.02366492\t1.114356046\t1.05993358\t1.044516909\t0.9908694581\t1.032466183\t1.032715105\t1.045373733\t1.082944576\t1.026358881\t1.04632205\t1.057547893\t1.016052993\t0.9957779607\t1.108413984\t1.055768451\t1.010963654\t1.043369855\t1.08307779\t1.049816966\t1.013796899\t1.022661593\t1.147047071\t1.04803357\t1.057980083\t1.040176021\t1.139616079\t1.096820207\t1.074053208\t1.07701842\t1.067895207\t1.045754471\t1.220421614\t1.092334667\t1.049895941\t1.105231283\t1.079012416\t1.029065154\t1.163461193\t1.000003471\t1.041891924\t1.110780152\t1.111676877\t1.04032492\t1.05290822\t1.050717747\t1.069244392\t1.090412037\t1.048492059\t1.056101833\t1.04779543\t1.037712824\t1.004778265\t1.037782207\t0.9939365153\t1.061741828\t1.01875415\t1.01310829\t1.032820366\t1.006853909\t1.041288979\t1.10767619\t1.042182301\t1.040163973\t1.078524467\t1.060273185\t1.037754502\t1.050921664\t1.038436938\t1.050437045\t1.086748415\t1.037915428\t1.069139647\t1.02829462\t1.080010704\t1.080233304\t1.077316084\t1.049028754\t1.034098296\t1.011190177\t1.078747658\n',
             'Data:\t0\t12151773\t3939\t1\t4641\t4930\t5931\t5879\t6554\t7942\t8636\t10006\t11334\t12882\t14850\t17672\t22610\t28015\t36699\t60607\t326385\t334346\t351046\t345737\t348739\t340001\t369450\t349981\t352712\t360359\t367661\t368505\t374701\t371052\t348087\t356881\t346025\t354646\t362061\t348531\t344573\t346213\t348286\t321619\t311895\t64255\t38581\t27813\t22530\t16580\t15755\t13655\t11094\t9107\t8481\t7027\t6458\t5403\t5325\t4667\t4578\t2251\t2513\t2358\t2223\t2500\t2709\t3440\t3596\t3720\t4207\t4131\t4844\t5071\t5740\t6062\t7605\t7419\t8458\t9892\t11292\t11805\t13419\t16414\t18326\t18158\t24115\t29000\t37924\t50446\t296306\t333661\t339280\t345588\t355961\t301506\t342899\t360451\t338689\t348015\t364987\t318808\t374701\t360042\t337894\t338544\t361971\t357978\t358503\t351574\t341551\t354613\t348230\t344170\t324700\t79384\t41123\t31922\t25077\t21882\t19177\t16254\t14639\t12992\t10612\t9463\t8844\t7166\t6743\t6437\t5342\t4672\t4728\t4255\t4277\t3689\t3556\t2928\t3115\t2756\t2566\t2495\t2414\t2002\t-129\t463\t1069\t1117\n']


with open('C:\\Users\\Oncobot\\Desktop\\test_file.prs', 'w') as outfile:
    for line in test_file:
        outfile.write(line)

if __name__ == "__main__":
    test_write_prs()
