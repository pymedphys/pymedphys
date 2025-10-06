###############
DVH (prototype)
###############

A small, focused DVH computation core intended for integration with PyMedPhys. This version provides:
- A clear `DVHConfig` to control binning, clipping and volume units.
- `compute_dvh` working from an aligned dose grid and voxel occupancy (boolean or fractional).
- Standard DVH metrics and interpolation helpers.
- Analytical DVHs for validation (linear-gradient cone/cylinder; sphere in Gaussian dose).
- A crude precision-band estimator to approximate the stair-step uncertainty.

## Quick demo
```bash
python -m pymedphys_dvh.cli --dose dose.npy --mask mask.npy --voxel-size-mm 1 1 1 --out-json dvh.json
```
