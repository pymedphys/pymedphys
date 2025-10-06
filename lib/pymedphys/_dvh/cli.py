# lib/pymedphys/_dvh/cli.py
from __future__ import annotations

import argparse

import numpy as np

from .config import DVHConfig
from .dicom_io import read_rtdose, read_rtstruct_as_rois
from .dvh import compute_dvh, dvh_metrics, precision_band
from .geometry.voxelise import voxelise_roi_to_mask


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="pymedphys-dvh",
        description="Compute DVH from RTSTRUCT + RTDOSE",
    )
    p.add_argument("--rtdose", required=True, help="Path to RTDOSE.dcm")
    p.add_argument("--rtstruct", required=True, help="Path to RTSTRUCT.dcm")
    p.add_argument("--roi", required=True, help="ROI name to compute (exact match)")
    p.add_argument("--bins", type=int, default=1000)

    p.add_argument(
        "--mode",
        choices=["right_prism", "sdf_linear"],
        default="right_prism",
        help="Voxelisation mode",
    )
    p.add_argument(
        "--endcaps",
        choices=["half_slice", "truncate"],
        default="half_slice",
        help="End‑cap handling along slice axis",
    )
    p.add_argument("--subxy", type=int, default=4, help="In‑plane supersample")
    p.add_argument("--subz", type=int, default=1, help="Axial supersample")
    p.add_argument(
        "--precision-band",
        action="store_true",
        help="Print an indicative DVH precision band (quantisation) based on sampling",
    )

    args = p.parse_args(argv)

    dose, geom, _ = read_rtdose(args.rtdose)
    rois = read_rtstruct_as_rois(args.rtstruct, geom)

    roi = next((r for r in rois if r.name == args.roi), None)
    if roi is None:
        names = ", ".join(r.name for r in rois)
        raise SystemExit(f"ROI '{args.roi}' not found. Available: {names}")

    endcaps = args.endcaps
    if endcaps == "none":
        # Backward‑compatibility alias
        endcaps = "truncate"

    cfg = DVHConfig(
        voxelise_mode=args.mode,
        endcap_mode=endcaps,
        inplane_supersample=args.subxy,
        axial_supersample=args.subz,
        dvh_bins=args.bins,
        subvoxel_dose_sample=True,
    )

    mask = voxelise_roi_to_mask(roi, geom, cfg)

    # Voxel spacing (approx) from dose grid metadata
    if len(geom.gfo) > 1:
        dz = float(geom.gfo[1] - geom.gfo[0])
    else:
        dz = 1.0
    voxel_mm = (geom.ps_row, geom.ps_col, dz)

    dose_axis, cum = compute_dvh(dose, mask, voxel_mm, cfg)

    # Volume in cc from fractional mask
    vtot_cc = float(mask.sum()) * (voxel_mm[0] * voxel_mm[1] * voxel_mm[2]) / 1000.0

    metrics = dvh_metrics(dose_axis, cum, vtot_cc)

    # Simple text output
    print(f"# ROI: {roi.name}")
    print(
        f"Vtotal (cc): {metrics['Vtotal_cc']:.4f}, "
        f"Dmean: {metrics['Dmean']:.3f} Gy, Dmax: {metrics['Dmax']:.3f} Gy"
    )

    for key in sorted(
        [k for k in metrics.keys() if k.startswith("D") and k not in ("Dmean", "Dmax")],
        key=lambda s: (len(s), s),
    ):
        print(f"{key}: {metrics[key]:.3f} Gy")

    if args.precision_band:
        # Effective sample count ~ number of voxels in mask times sub‑samples
        n_vox = int(np.count_nonzero(mask > 0.0))
        n_eff = n_vox * max(1, args.subz) * max(1, args.subxy) * max(1, args.subxy)
        lo, hi = precision_band(dose_axis, cum, n_eff)
        print(f"# Precision band (quantisation, n_eff={n_eff}):")
        print(f"lower[0], upper[0]: {lo[0]:.6f}, {hi[0]:.6f}")
        print(f"lower[-1], upper[-1]: {lo[-1]:.6f}, {hi[-1]:.6f}")


if __name__ == "__main__":
    main()
