from __future__ import annotations

import argparse

from .config import DVHConfig
from .dicom_io import read_rtdose, read_rtstruct_as_rois
from .dvh import compute_dvh, dvh_metrics
from .geometry.voxelise import voxelise_roi_to_mask


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="pymedphys-dvh", description="Compute DVH from RTSTRUCT + RTDOSE"
    )
    p.add_argument("--rtdose", required=True, help="Path to RTDOSE.dcm")
    p.add_argument("--rtstruct", required=True, help="Path to RTSTRUCT.dcm")
    p.add_argument("--roi", required=True, help="ROI name to compute (exact match)")
    p.add_argument("--bins", type=int, default=1000)
    p.add_argument(
        "--mode", choices=["right_prism", "sdf_linear"], default="right_prism"
    )
    p.add_argument("--endcaps", choices=["half_slice", "none"], default="half_slice")
    p.add_argument("--subxy", type=int, default=4)
    p.add_argument("--subz", type=int, default=1)
    args = p.parse_args(argv)

    dose, geom, _ = read_rtdose(args.rtdose)
    rois = read_rtstruct_as_rois(args.rtstruct, geom)
    roi = next((r for r in rois if r.name == args.roi), None)
    if roi is None:
        names = ", ".join(r.name for r in rois)
        raise SystemExit(f"ROI '{args.roi}' not found. Available: {names}")

    cfg = DVHConfig(
        voxelise_mode=args.mode,
        endcap_mode=args.endcaps,
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
    edges, cum = compute_dvh(dose, mask, voxel_mm, cfg)
    Vtot = float(mask.sum()) * (voxel_mm[0] * voxel_mm[1] * voxel_mm[2]) / 1000.0
    metrics = dvh_metrics(edges, cum, Vtot)

    # Simple text output
    print(f"# ROI: {roi.name}")
    print(
        f"Vtotal (cc): {metrics['Vtotal_cc']:.4f}, Dmean: {metrics['Dmean']:.3f} Gy, Dmax: {metrics['Dmax']:.3f} Gy"
    )
    for key in sorted(
        [k for k in metrics.keys() if k.startswith("D") and k not in ("Dmean", "Dmax")],
        key=lambda s: (len(s), s),
    ):
        print(f"{key}: {metrics[key]:.3f} Gy")


if __name__ == "__main__":
    main()
