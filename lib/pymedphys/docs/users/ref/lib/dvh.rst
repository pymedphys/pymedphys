##########################
DVH (prototype / research)
##########################

A small, focused DVH computation core intended for integration with PyMedPhys.

This module provides:

* A clear :class:`pymedphys._dvh.config.DVHConfig` to control binning, end‑capping and voxelisation mode.
* :func:`pymedphys._dvh.dvh.compute_dvh` producing **fractional** cumulative DVHs (0..1) from a dose grid and
  a boolean/fractional mask.
* :func:`pymedphys._dvh.dvh.dvh_metrics` returning ``Dmin``, ``Dmax``, ``Dmean``, standard percent metrics
  (e.g. ``D1``, ``D5``, ``D95``, ``D99``) and absolute‑volume metrics (``D0.03cc``).
* **Analytical DVHs** for commissioning and regression (linear‑gradient cone/cylinder; sphere in Gaussian dose).
* A pragmatic **precision band** API (:func:`pymedphys._dvh.dvh.precision_band`) that communicates DVH
  quantisation uncertainty (±½ step with ``n_eff`` samples).

Methodological context: see Nelms et al. (analytical closed‑forms, end‑capping and validation datasets). :contentReference[oaicite:3]{index=3}

Quick start (CLI)
=================

.. code-block:: bash

   pymedphys-dvh \
     --rtdose RTDOSE.dcm \
     --rtstruct RTSTRUCT.dcm \
     --roi "PTV_7000" \
     --bins 2000 \
     --mode right_prism \
     --endcaps half_slice \
     --subxy 4 --subz 1 \
     --precision-band

The output reports ``Vtotal (cc)``, ``Dmean``, ``Dmax``, then per‑metric ``Dxx`` and (optionally) a
precision band sample.

Python API
==========

.. code-block:: python

   import pydicom
   from pymedphys._dvh import DVHConfig
   from pymedphys._dvh.dicom_io import read_rtdose, read_rtstruct_as_rois
   from pymedphys._dvh.geometry.voxelise import voxelise_roi_to_mask
   from pymedphys._dvh.dvh import compute_dvh, dvh_metrics, precision_band

   dose, geom, _ = read_rtdose("RTDOSE.dcm")
   rois = read_rtstruct_as_rois("RTSTRUCT.dcm", geom)
   roi = next(r for r in rois if r.name == "PTV_7000")

   cfg = DVHConfig(voxelise_mode="right_prism", endcap_mode="half_slice",
                   inplane_supersample=4, axial_supersample=1,
                   dvh_bins=2000, subvoxel_dose_sample=True)

   mask = voxelise_roi_to_mask(roi, geom, cfg)
   dz = (geom.gfo[1] - geom.gfo[0]) if len(geom.gfo) > 1 else 1.0
   dose_axis, cum = compute_dvh(dose, mask, (geom.ps_row, geom.ps_col, dz), cfg)

   vtot_cc = float(mask.sum()) * (geom.ps_row * geom.ps_col * dz) / 1000.0
   metrics = dvh_metrics(dose_axis, cum, vtot_cc)

   n_eff = int((mask > 0).sum()) * cfg.inplane_supersample**2 * cfg.axial_supersample
   lo, hi = precision_band(dose_axis, cum, n_eff)

Notes
=====

* **End‑caps**: ``endcap_mode="half_slice"`` extends the superior/inferior caps by half the local
  slice spacing, consistent with how many TPSs are observed to behave in practice, and the choice used
  in the Nelms commissioning paper. :contentReference[oaicite:4]{index=4}
* **Rings/holes**: Multiple contours in a plane are rasterised with even‑odd parity, so inner rings act as holes.
* **Dmean** is computed as the integral of the cumulative DVH (fraction) over dose; cumulative DVHs are enforced
  non‑increasing to be robust against minute interpolation noise at steep gradients.

Commissioning tips
==================

* Use the included analytical cases (linear gradient cylinder/cone; Gaussian‑in‑sphere) to commission and
  regress the DVH engine. :contentReference[oaicite:5]{index=5}
* When reporting DVHs to clinicians, include a **precision band** so discretisation effects are explicit, and
  state the dose bin width and voxelisation parameters.
