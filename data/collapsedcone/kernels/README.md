# The convolution kernels

## Attribution

Kernel's provided by Dr. Thomas R. Mackie

## Description

The data here is stored in two forms, firslty its original form as provided
by Dr Mackie, and secondly in yaml format for loading into Python.

## Original data descrition

Convolution kernels or "dose spread arrays" describe the distribution of dose
deposited when primary photons interact at one location in a spherical phantom.
They were generated in 1985 using the EGS3  Monte Carlo routine called scasph
(short for scatter spherical) written by Alex Bielajew at the National Research
Council of Canada (NRCC) in Ottawa. The program keeps track of a number of
scattering orders and categories of photons generated.

The kernels have been stored in files called `scafxxx` where `xxx` stands
for the photon energy.

The following categories of dose are tabulated:

1 - primary
2 - 1st scatter
3 - 2nd scatter
4 - multiple scatter
5 - bremsstrahlung plus annihilation dose
6 - mean radius for the primary dose voxels
7 - mean angle for the primary dose voxels

The following photon energies have been run (MeV):

0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80, 1.00, 1.25, 1.50, 2.0, 3.0,
4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0

The voxels for the convolution kernels are in spherical coordinates. The
boundaries are defined by the following radii expressed in radiological
distance:

0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80, 1.0, 1.5, 2.0, 3.0, 4.0,
5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0

The radial boundaries are stored in a file named `voxels.dat`. This
file is used by the data manipulation and convolution/superposition software.

The spherical voxel boundaries are defined by 48 evenly spaced conical angles
(with respect to the primary photon direction) in degrees:

3.75  (ie. 1/48 of 180 )
7.50  
11.25
.
.
.
180  (ie. 48/48 of 180 )
