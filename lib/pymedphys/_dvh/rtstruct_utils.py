# src/dvhtools/rtstruct.py

"""
RTSTRUCT parsing and ROI extraction utilities.
"""

import numpy as np
import pydicom
import numba as nb
from typing import Any, Dict, List, Tuple, Union


@nb.njit(cache=True, fastmath=True)
def is_inside_polygon(
    polygon: np.ndarray,
    point: Union[Tuple[float, float], np.ndarray],
    include_edges: bool = True,
) -> bool:
    """
    Determine whether a 2D point lies inside a closed polygon.

    Parameters
    ----------
    polygon : ndarray[N,2]
        Vertices of a closed polygon, with polygon[0] == polygon[-1].
    point : (x, y) tuple or length-2 ndarray
        Query point in same coordinate frame as `polygon`.
    include_edges : bool, default=True
        - True: treat points exactly on an edge or vertex as INSIDE.
        - False: treat boundary points as OUTSIDE.

    Returns
    -------
    bool
        True if `point` is inside (or on the boundary, if include_edges=True);
        otherwise False.
    """
    length = len(polygon) - 1
    dy2 = point[1] - polygon[0, 1]
    intersections = 0

    for i in range(length):
        j = i + 1
        dy = dy2
        dy2 = point[1] - polygon[j, 1]

        # consider only edges that cross a leftward horizontal ray
        if dy * dy2 <= 0.0 and (point[0] >= polygon[i, 0] or point[0] >= polygon[j, 0]):
            # non-horizontal segment
            if dy < 0 or dy2 < 0:
                F = dy * (polygon[j, 0] - polygon[i, 0]) / (dy - dy2) + polygon[i, 0]
                if point[0] > F:
                    intersections += 1
                elif point[0] == F:
                    # exactly on segment
                    return include_edges
            # horizontal segment or vertex case
            elif dy2 == 0 and (
                point[0] == polygon[j, 0]
                or (
                    dy == 0
                    and (point[0] - polygon[i, 0]) * (point[0] - polygon[j, 0]) <= 0
                )
            ):
                return include_edges

    # odd-even rule for strict inside
    return (intersections & 1) == 1


def rois_from_rtstruct(
    rtstruct: pydicom.dataset.Dataset,
) -> Dict[str, Any]:
    """
    Extract ROI metadata and contours from an RTSTRUCT DICOM.

    Parameters
    ----------
    rtstruct : pydicom.dataset.Dataset
        A loaded DICOM RTSTRUCT dataset (Modality=='RTSTRUCT').

    Returns
    -------
    dict[str, Any]
        Mapping from ROI number (as string) to a dict with keys:
          - "Name": ROIName (str)
          - "Type": RTROIInterpretedType (str)
          - "Colour": ROIDisplayColor or "Unspecified" (str)
          - "Contours": dict[z_str → ndarray[N,2]] or None
          - "Vertices": ndarray[M,3] of all contour pts or None

    Raises
    ------
    ValueError
        If `rtstruct.Modality` is not "RTSTRUCT".
    """
    if getattr(rtstruct, "Modality", None) != "RTSTRUCT":
        raise ValueError("Input must be a DICOM dataset of modality 'RTSTRUCT'")

    rois: Dict[str, Any] = {}

    # 1) Build initial ROI entries from StructureSetROISequence + Observations
    for ssr in rtstruct.StructureSetROISequence:
        obs = next(
            ro
            for ro in rtstruct.RTROIObservationsSequence
            if ro.ReferencedROINumber == ssr.ROINumber
        )
        key = str(ssr.ROINumber)
        rois[key] = {
            "Name": str(ssr.ROIName),
            "Type": str(obs.RTROIInterpretedType),
        }

    # 2) Attach contour‐sequence data if requested
    for rc in rtstruct.ROIContourSequence:
        key = str(rc.ReferencedROINumber)
        if key not in rois:
            continue

        colour = rc.ROIDisplayColor if hasattr(rc, "ROIDisplayColor") else "Unspecified"
        rois[key]["Colour"] = str(colour)

        contours: Dict[str, np.ndarray] = {}
        verts_list: List[np.ndarray] = []
        for c in rc.ContourSequence:
            data = np.array(c.ContourData, dtype=np.float64)
            pts = data.reshape(-1, 3)
            z = float(pts[0, 2])
            xy = pts[:, :2]
            contours[str(z)] = xy
            verts_list.append(pts)
        rois[key]["Contours"] = contours
        rois[key]["Vertices"] = np.vstack(verts_list)

    return rois
