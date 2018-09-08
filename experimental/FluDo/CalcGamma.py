import npgamma
import numpy as np
import matplotlib.pyplot as plt


DoseRef=np.ndarray([5,5])
for x in range(0,5,1):
    for y in range(0,5,1):
        DoseRef[x][y]=1.0*x*y

Xref=np.linspace(-2.5,2.5,5)
Yref=Xref

DoseEval=DoseRef*0.03

coords_reference =(Xref,Yref)
coords_evaluation=coords_reference

distance_threshold = 2
distance_step_size = distance_threshold / 10

dose_threshold = 0.02 * np.max(DoseRef)

lower_dose_cutoff = np.max(DoseEval) * 0.2

if __name__=='__main__':
    gamma=npgamma.calc_gamma(
    coords_reference, DoseRef,
    coords_evaluation, DoseEval,
    distance_threshold, dose_threshold,
    lower_dose_cutoff=lower_dose_cutoff,
    distance_step_size=distance_step_size,
    maximum_test_distance=np.inf)

    valid_gamma = gamma[~np.isnan(gamma)]
    valid_gamma[valid_gamma > 2] = 2

    plt.hist(valid_gamma, 30);
    plt.xlim([0,2])
    plt.show()
    print(np.sum(valid_gamma <= 1) / len(valid_gamma),'Gamma')







