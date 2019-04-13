import matplotlib.pyplot as plt

from pymedphys.mudensity import single_mlc_pair

mlc_left = (-2.3, 3.1)  # (start position, end position)
mlc_right = (0, 7.7)

x, mu_density = single_mlc_pair(mlc_left, mlc_right)
plt.plot(x, mu_density, '-o')
plt.title('A single MLC')
plt.xlabel('MLC direction (mm)')
plt.ylabel('Open fraction')
