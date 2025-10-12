# pymedphys/_dvh/dicom_io.py
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
from numpy.typing import NDArray

try:
    import pydicom
    from pydicom.dataset import Dataset
    from pydicom.sequence import Sequence as DicomSequence
except Exception as e:  # pragma: no cover - import error surfaced clearly to the user
    raise RuntimeError(
        "pydicom is required for DVH DICOM I/O. Please add 'pydicom' to your environment."
    ) from e

from .types import DicomStudy, DoseGrid, ImageVolume, Structure3D, StructureContour

__all__ = [
    "load_rt_dose",
    "load_rtstruct",
    "load_ct_series",
    "load_study",
]


PathLike = Union[str, Path]
DsLike = Union[Dataset, PathLike]


def _as_dataset(obj: DsLike) -> Dataset:
    if isinstance(obj, Dataset):
        return obj
    return pydicom.dcmread(str(obj), force=True)


def _orientation_matrix_from_iop(iop: Sequence[float]) -> NDArray[np.floating]:
    """Return a (3,3) matrix with columns (row, col, normal) direction cosines."""
    iop = np.asarray(iop, dtype=float)
    if iop.size != 6:
        raise ValueError("ImageOrientationPatient must have 6 elements.")
    row = iop[0:3]
    col = iop[3:6]
    # Normal = row × col (DICOM standard)
    normal = np.cross(row, col)
    # Normalise to guard against roundoff
    row = row / np.linalg.norm(row)
    col = col / np.linalg.norm(col)
    normal = normal / np.linalg.norm(normal)
    return np.column_stack([row, col, normal])


def load_rt_dose(ds_or_path: DsLike) -> DoseGrid:
    """
    Load a DICOM RT Dose object into a DoseGrid (Gy, LPS).

    Notes
    -----
    - Uses DoseGridScaling and assumes DoseUnits == 'GY'. If DoseUnits is 'RELATIVE',
      values are scaled to 'Gy-equivalent' only if a prescription is supplied later by the caller.
    - Multi-frame dose is expected (NumberOfFrames >= 1) with GridFrameOffsetVector.
    """
    ds = _as_dataset(ds_or_path)

    if str(getattr(ds, "SOPClassUID", "")).strip() != "1.2.840.10008.5.1.4.1.1.481.2":
        warnings.warn(
            "SOPClassUID is not RT Dose (481.2); proceeding anyway for test/compat use."
        )

    rows = int(ds.Rows)
    cols = int(ds.Columns)
    nframes = int(getattr(ds, "NumberOfFrames", 1))

    # Pixel data: favour raw buffer to avoid optional jpeg libraries
    bits_alloc = int(getattr(ds, "BitsAllocated", 16))
    if bits_alloc not in (16, 32):
        raise ValueError(f"Unsupported BitsAllocated={bits_alloc}.")
    dtype = np.uint16 if bits_alloc == 16 else np.uint32
    raw = np.frombuffer(ds.PixelData, dtype=dtype)
    expected = rows * cols * nframes
    if raw.size != expected:
        raise ValueError(
            f"RTDOSE PixelData length mismatch ({raw.size} != {expected})."
        )
    raw = raw.reshape((nframes, rows, cols))

    grid_scale = float(getattr(ds, "DoseGridScaling", 1.0))
    values_gy = raw.astype(np.float32) * grid_scale

    # Geometry
    ipp = np.asarray(getattr(ds, "ImagePositionPatient", [0.0, 0.0, 0.0]), dtype=float)
    iop = np.asarray(
        getattr(ds, "ImageOrientationPatient", [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]),
        dtype=float,
    )
    ps = np.asarray(getattr(ds, "PixelSpacing", [1.0, 1.0]), dtype=float)

    # DICOM PixelSpacing = (row_spacing, col_spacing) == (dy, dx)
    dy, dx = float(ps[0]), float(ps[1])

    # Offsets: (GridFrameOffsetVector) relative to frame 0 plane, mm
    offsets = np.asarray(getattr(ds, "GridFrameOffsetVector", [0.0]), dtype=float)
    if offsets.size != nframes:
        # Fallback: infer uniform spacing from SliceThickness / SpacingBetweenSlices
        dz = float(getattr(ds, "SliceThickness", 1.0))
        offsets = np.arange(nframes, dtype=float) * dz

    orient = _orientation_matrix_from_iop(iop)
    # dz nominal: mean of diffs, kept in spacing tuple for metadata only
    dz_nominal = (
        float(np.mean(np.abs(np.diff(offsets))))
        if nframes > 1
        else float(getattr(ds, "SliceThickness", 1.0))
    )

    dose = DoseGrid(
        values=values_gy,
        origin_ipp_mm=ipp.astype(np.float64),
        orientation_matrix=orient.astype(np.float64),
        spacing_mm=(dx, dy, dz_nominal),
        frame_offsets_mm=offsets.astype(np.float64),
        dose_units=str(getattr(ds, "DoseUnits", "GY")).upper(),
        frame_of_reference_uid=getattr(ds, "FrameOfReferenceUID", None),
        sop_instance_uid=getattr(ds, "SOPInstanceUID", None),
    )
    return dose


def load_rtstruct(
    ds_or_path: DsLike,
    include_names: Optional[Iterable[str]] = None,
    z_merge_tol_mm: float = 1e-3,
) -> Dict[str, Structure3D]:
    # ... [existing parsing as previously provided] ...
    ds = _as_dataset(ds_or_path)

    name_by_number: Dict[int, str] = {}
    for item in getattr(ds, "StructureSetROISequence", []):
        number = int(item.ROINumber)
        name = str(getattr(item, "ROIName", f"ROI_{number}"))
        name_by_number[number] = name

    # Prefer per-ROI FOR UID; fall back to top-level if present
    for_uid_fallback = None
    for for_item in getattr(ds, "ReferencedFrameOfReferenceSequence", []) or []:
        uid = getattr(for_item, "FrameOfReferenceUID", None)
        if uid:
            for_uid_fallback = str(uid)
            break

    wanted = set(include_names) if include_names is not None else None
    out: Dict[str, Structure3D] = {}

    for rc in getattr(ds, "ROIContourSequence", []):
        roi_num = int(rc.ReferencedROINumber)
        roi_name = name_by_number.get(roi_num, f"ROI_{roi_num}")
        if wanted is not None and roi_name not in wanted:
            continue

        # Per-ROI FOR UID if present
        rois = [
            s
            for s in getattr(ds, "StructureSetROISequence", [])
            if int(s.ROINumber) == roi_num
        ]
        for_uid = (
            str(getattr(rois[0], "ReferencedFrameOfReferenceUID", "")) if rois else None
        )
        if not for_uid:
            for_uid = for_uid_fallback

        struct = out.get(roi_name) or Structure3D(
            name=roi_name, number=roi_num, frame_of_reference_uid=for_uid
        )

        for cs in getattr(rc, "ContourSequence", []):
            pts = np.asarray(cs.ContourData, dtype=float).reshape(-1, 3)
            ring = StructureContour.from_points(pts)
            z = ring.z_mm
            # Merge to an existing plane if within tolerance
            if struct.planes:
                existing = np.array(struct.plane_zs(), dtype=float)
                diffs = np.abs(existing - z)
                if diffs.size > 0 and np.min(diffs) <= z_merge_tol_mm:
                    z = float(existing[np.argmin(diffs)])
            struct.add_ring(z, ring)

        # --- Step 3: Sanity checks & warnings on spacing and few-slice ---
        zs = struct.plane_zs()
        if len(zs) <= 7:
            warnings.warn(
                f"Structure '{roi_name}' has only {len(zs)} axial slice(s) (<= 7). "
                "Expect increased DVH variability for small volumes/sparse sampling.",
                stacklevel=2,
            )
        if len(zs) >= 3:
            spacings = [float(b - a) for a, b in zip(zs[:-1], zs[1:])]
            if (max(spacings) - min(spacings)) > 0.2:
                warnings.warn(
                    f"Non-uniform inter-slice spacing for '{roi_name}' varies by "
                    f"{(max(spacings) - min(spacings)):.3f} mm (>0.2 mm).",
                    stacklevel=2,
                )

        out[roi_name] = struct

    return out


def load_ct_series(datasets_or_paths: Sequence[DsLike]) -> ImageVolume:
    """
    Load minimal CT geometry from a list/sequence of slices.

    Parameters
    ----------
    datasets_or_paths : sequence of pydicom.Dataset or paths
        CT slices belonging to one series, any order.

    Returns
    -------
    ImageVolume
        Minimal geometry object (no pixel data) for consistency checks and, if desired,
        to infer local half-slice end-cap spacing elsewhere.
    """
    dsets = [_as_dataset(d) for d in datasets_or_paths]
    if not dsets:
        raise ValueError("No CT slices provided.")

    # Sort by ImagePositionPatient projected onto normal
    iop = np.asarray(
        getattr(dsets[0], "ImageOrientationPatient", [1, 0, 0, 0, 1, 0]), dtype=float
    )
    orient = _orientation_matrix_from_iop(iop)
    ipp0 = np.asarray(
        getattr(dsets[0], "ImagePositionPatient", [0.0, 0.0, 0.0]), dtype=float
    )
    norm = orient[:, 2]
    dy, dx = map(float, getattr(dsets[0], "PixelSpacing", [1.0, 1.0]))
    for d in dsets[1:]:
        iop_i = np.asarray(getattr(d, "ImageOrientationPatient", iop), dtype=float)
        if not np.allclose(iop_i, iop, atol=1e-5):
            warnings.warn(
                "CT series contains varying ImageOrientationPatient; using first slice."
            )
            break

    # Compute positions along normal relative to first slice
    pos = []
    for d in dsets:
        ipp = np.asarray(getattr(d, "ImagePositionPatient", ipp0), dtype=float)
        pos.append(float(np.dot(ipp - ipp0, norm)))
    pos = np.asarray(pos, dtype=float)
    order = np.argsort(pos)
    pos = pos[order]

    vol = ImageVolume(
        origin_ipp_mm=ipp0.astype(np.float64),
        orientation_matrix=orient.astype(np.float64),
        pixel_spacing_mm=(dy, dx),
        slice_positions_mm=pos.astype(np.float64),
        frame_of_reference_uid=getattr(dsets[0], "FrameOfReferenceUID", None),
    )
    return vol


def load_study(
    rtstruct: DsLike,
    rtdose: DsLike,
    ct_slices: Optional[Sequence[DsLike]] = None,
    include_names: Optional[Iterable[str]] = None,
) -> DicomStudy:
    """
    Load a minimal DVH 'study' of Dose + Structures (+ optional CT geometry).

    Parameters
    ----------
    rtstruct : Dataset or path
    rtdose : Dataset or path
    ct_slices : optional sequence of CT slices or paths
    include_names : iterable of ROIName to include; if None, include all

    Returns
    -------
    DicomStudy
    """
    dose = load_rt_dose(rtdose)
    structs = load_rtstruct(rtstruct, include_names=include_names)
    ct = load_ct_series(ct_slices) if ct_slices else None

    # Frame-of-reference sanity check (advisory)
    dose_for = getattr(dose, "frame_of_reference_uid", None)
    if dose_for:
        mismatched = [
            s.name
            for s in structs.values()
            if s.frame_of_reference_uid and s.frame_of_reference_uid != dose_for
        ]
        if mismatched:
            warnings.warn(
                "FrameOfReferenceUID mismatch between RTSTRUCT and RTDOSE for: "
                + ", ".join(mismatched)
            )

    return DicomStudy(dose=dose, structures=structs, ct=ct)
