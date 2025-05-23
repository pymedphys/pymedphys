import os
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import plotly.graph_objects as go
import pydicom
import streamlit as st

st.set_page_config(layout="wide")

st.title("Interactive DICOM RT Viewer")

DEFAULT_WINDOW_LEVEL: int = 0
DEFAULT_WINDOW_WIDTH: int = 500


@dataclass
class CTSlice:
    SeriesInstanceUID: str
    ImagePositionPatient: Tuple[float, float, float]
    ImageOrientationPatient: Tuple[float, float, float, float, float, float]
    PixelSpacing: Tuple[float, float]
    Rows: int
    Columns: int
    PixelArray: np.ndarray
    RescaleSlope: float = 1.0
    RescaleIntercept: float = 0.0
    WindowCenter: int = 0
    WindowWidth: int = 500
    BitsStored: int = 16

    def __post_init__(self):
        assert self.Rows > 0, "Rows must be positive."
        assert self.Columns > 0, "Columns must be positive."
        assert (
            len(self.ImagePositionPatient) == 3
        ), "ImagePositionPatient must be a 3-tuple."
        assert (
            len(self.ImageOrientationPatient) == 6
        ), "ImageOrientationPatient must be a 6-tuple."
        assert len(self.PixelSpacing) == 2, "PixelSpacing must be a 2-tuple."


def preprocess_ct_slice_datasets(
    ct_slice_datasets: Sequence[pydicom.dataset.FileDataset],
) -> List[CTSlice]:
    """
    Preprocess and extract necessary attributes from CT slice datasets.

    Args:
        ct_slice_datasets (Sequence[pydicom.dataset.FileDataset]): Sequence of DICOM datasets representing CT slices.

    Returns:
        List[CTSlice]: A list of CTSlice dataclass instances containing preprocessed CT slice data.

    Raises:
        ValueError: If no valid CT slices are found after preprocessing.
    """
    preprocessed_data = []
    for idx, ds in enumerate(ct_slice_datasets):
        try:
            preprocessed_slice = CTSlice(
                SeriesInstanceUID=ds.SeriesInstanceUID,
                ImagePositionPatient=tuple(ds.ImagePositionPatient),
                ImageOrientationPatient=tuple(ds.ImageOrientationPatient),
                PixelSpacing=tuple(ds.PixelSpacing),
                Rows=ds.Rows,
                Columns=ds.Columns,
                PixelArray=ds.pixel_array,  # Keep original dtype
                RescaleSlope=float(getattr(ds, "RescaleSlope", 1.0)),
                RescaleIntercept=float(getattr(ds, "RescaleIntercept", 0.0)),
                WindowCenter=float(
                    getattr(ds, "WindowCenter", DEFAULT_WINDOW_LEVEL)[0]
                ),
                WindowWidth=float(getattr(ds, "WindowWidth", DEFAULT_WINDOW_WIDTH)[0]),
                BitsStored=int(getattr(ds, "BitsStored", 16)),
            )
            preprocessed_data.append(preprocessed_slice)
        except AttributeError as e:
            st.warning(
                f"Missing attribute in CT slice {idx + 1}: {e}. This slice will be skipped."
            )
        except Exception as unknown_e:
            st.warning(
                f"Failure processing in CT slice {idx + 1}: {unknown_e}. This slice will be skipped."
            )
    if not preprocessed_data:
        raise ValueError("No valid CT slices found after preprocessing.")
    return preprocessed_data


def check_only_one_ct_series(preprocessed_data: Sequence[CTSlice]) -> None:
    """
    Ensure all CT slices belong to the same series.

    Args:
        preprocessed_data (Sequence[CTSlice]): Preprocessed CT slice data.

    Raises:
        ValueError: If CT slices belong to different SeriesInstanceUIDs.
    """
    series_uid = preprocessed_data[0].SeriesInstanceUID
    for idx, data in enumerate(preprocessed_data[1:], start=2):
        if data.SeriesInstanceUID != series_uid:
            raise ValueError(
                f"CT slice {idx} has a different SeriesInstanceUID. All slices must belong to the same series."
            )


def check_all_slices_aligned(preprocessed_data: Sequence[CTSlice]) -> None:
    """
    Ensure all CT slices are aligned in position, orientation, and spacing.

    Args:
        preprocessed_data (Sequence[CTSlice]): Preprocessed CT slice data.

    Raises:
        ValueError: If CT slices are misaligned in position, orientation, or spacing.
    """
    ref_position = preprocessed_data[0].ImagePositionPatient[:2]
    ref_orientation = preprocessed_data[0].ImageOrientationPatient
    ref_spacing = preprocessed_data[0].PixelSpacing

    for idx, data in enumerate(preprocessed_data[1:], start=2):
        if data.ImagePositionPatient[:2] != ref_position:
            raise ValueError(
                f"CT slice {idx} has a different ImagePositionPatient. All slices must be aligned."
            )
        if data.ImageOrientationPatient != ref_orientation:
            raise ValueError(
                f"CT slice {idx} has a different ImageOrientationPatient. All slices must have the same orientation."
            )
        if data.PixelSpacing != ref_spacing:
            raise ValueError(
                f"CT slice {idx} has a different PixelSpacing. All slices must have the same pixel spacing."
            )


@st.cache_data(show_spinner=False, persist=True)
def compute_patient_coordinates(
    height: int,
    width: int,
    ipp: Tuple[float, float, float],
    iop: Tuple[float, float, float],
    pixel_spacing: Tuple[float, float],
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute patient coordinates for the CT image using matrix multiplication.

    Args:
        height (int): Number of rows in the CT image.
        width (int): Number of columns in the CT image.
        ipp (Tuple[float, float, float]): Image Position Patient (X, Y, Z).
        iop (Tuple[float, float, float]): Image Orientation Patient (row cosine components).
        pixel_spacing (Tuple[float, float]): Pixel spacing in millimeters (row spacing, column spacing).

    Returns:
        Tuple[np.ndarray, np.ndarray]: Arrays representing the X and Y coordinates in patient space.

    Raises:
        ValueError: If scaling Image Orientation Patient (IOP) with Pixel Spacing fails.
    """
    ipp_np = np.array(ipp, dtype=np.float32)
    iop_np = np.array(iop, dtype=np.float32).reshape(2, 3)
    pixel_spacing_np = np.array(pixel_spacing, dtype=np.float32)

    # Scale row and column cosines by pixel spacing
    try:
        iop_scaled = iop_np.T @ np.diag(pixel_spacing_np)  # Shape: (3, 2)
    except ValueError as e:
        raise ValueError(f"Error in scaling IOP with Pixel Spacing: {e}") from e

    # Create meshgrid of pixel indices
    jj, ii = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
        indexing="xy",
    )

    # Stack the pixel indices and compute physical coordinates
    indices = np.stack([jj.ravel(), ii.ravel()], axis=0)  # Shape: (2, height * width)
    coordinates = ipp_np[:, None] + iop_scaled @ indices  # Shape: (3, height * width)

    # Reshape coordinates to (height, width)
    X = coordinates[0].reshape(height, width)
    Y = coordinates[1].reshape(height, width)

    return X, Y


@st.cache_data(show_spinner=True, persist=True)
def load_ct_as_memmap(
    dirpath: str | os.PathLike, memmap_file: str = "ct_volume.dat"
) -> Tuple[
    np.memmap, List[Dict[str, Any]], np.ndarray, np.ndarray, float, float, int, int
]:
    """
    Load CT slices as a memory-mapped array and cache the operation.

    Args:
        dirpath (str | os.PathLike): Path to the directory containing CT DICOM files.
        memmap_file (str, optional): Filename for the memory-mapped file. Defaults to "ct_volume.dat".

    Returns:
        Tuple[np.memmap, List[Dict[str, Any]], np.ndarray, np.ndarray, float, float, int, int]:
            - memmap: Memory-mapped array of CT image data.
            - ct_headers: List of CT slice headers with spatial information.
            - X: X coordinates array.
            - Y: Y coordinates array.
            - pixel_min: Minimum pixel value in the CT volume.
            - pixel_max: Maximum pixel value in the CT volume.
            - wl_default: Default Window Level.
            - ww_default: Default Window Width.

    Raises:
        ValueError: If no valid CT slices are found.
        RuntimeError: If memory-mapped file creation or loading fails.
    """
    dirpath = pathlib.Path(dirpath)

    ct_slice_datasets = []
    for fpath in sorted(dirpath.glob("*.dcm")):
        try:
            ds = pydicom.dcmread(fpath)
            if ds.Modality == "CT":
                ct_slice_datasets.append(ds)
        except pydicom.errors.InvalidDicomError:
            st.warning(
                f"File {fpath.name} is not a valid DICOM file and will be skipped."
            )
        except Exception as e:
            st.warning(f"Error reading {fpath.name}: {e}. This file will be skipped.")

    if not ct_slice_datasets:
        raise ValueError("No valid CT slices found in the provided directory.")

    preprocessed_data = preprocess_ct_slice_datasets(ct_slice_datasets)

    check_only_one_ct_series(preprocessed_data)
    check_all_slices_aligned(preprocessed_data)

    # Sort slices based on ImagePositionPatient Z-coordinate
    preprocessed_data.sort(key=lambda data: data.ImagePositionPatient[2])

    num_slices = len(preprocessed_data)
    height = preprocessed_data[0].Rows
    width = preprocessed_data[0].Columns

    memmap_path = dirpath / memmap_file

    # Determine dtype based on BitsStored
    bits_stored_set = set(slice_data.BitsStored for slice_data in preprocessed_data)
    if len(bits_stored_set) > 1:
        raise ValueError("CT slices have differing BitsStored values.")

    bits_stored = bits_stored_set.pop()

    if bits_stored <= 16:
        dtype = np.int16
        st.info(f"Selected dtype: {dtype} based on BitsStored={bits_stored}")
    else:
        dtype = np.float32
        st.info(f"Selected dtype: {dtype} based on BitsStored={bits_stored}")

    if not memmap_path.exists():
        try:
            memmap = np.memmap(
                memmap_path,
                dtype=dtype,
                mode="w+",
                shape=(num_slices, height, width),
            )
            for i, data in enumerate(preprocessed_data):
                # Rescale the pixel data
                rescaled = data.PixelArray * data.RescaleSlope + data.RescaleIntercept
                if dtype == np.int16:
                    rescaled = rescaled.astype(np.int16)
                elif dtype == np.float32:
                    rescaled = rescaled.astype(np.float32)
                memmap[i, :, :] = rescaled
            memmap.flush()
            st.info(f"CT volume data saved to {memmap_path}.")
        except Exception as e:
            raise RuntimeError(f"Failed to create memory-mapped file: {e}") from e
    else:
        try:
            memmap = np.memmap(
                memmap_path,
                dtype=dtype,
                mode="r",
                shape=(num_slices, height, width),
            )
            st.info(f"CT volume data loaded from existing memmap file {memmap_path}.")
        except Exception as e:
            raise RuntimeError(f"Failed to load memory-mapped file: {e}") from e

    first_data = preprocessed_data[0]
    pixel_min = float(memmap.min())
    pixel_max = float(memmap.max())

    wl_default = int(first_data.WindowCenter)
    ww_default = int(first_data.WindowWidth)

    try:
        X, Y = compute_patient_coordinates(
            height,
            width,
            first_data.ImagePositionPatient,
            first_data.ImageOrientationPatient,
            first_data.PixelSpacing,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to compute patient coordinates: {e}") from e

    ct_headers = []
    for data in preprocessed_data:
        try:
            ct_headers.append(
                {
                    "ipp": data.ImagePositionPatient,
                    "iop": data.ImageOrientationPatient,
                    "spacing": data.PixelSpacing,
                }
            )
        except Exception as e:
            st.warning(f"Error processing CT header data: {e}")

    return memmap, ct_headers, X, Y, pixel_min, pixel_max, wl_default, ww_default


@st.cache_data(show_spinner=True, persist=True)
def load_rt_structures(fpath: str | os.PathLike) -> Dict[str, Dict[str, Any]]:
    """
    Load RT structures from a RTSTRUCT DICOM file and cache the results.

    Args:
        fpath (str | os.PathLike): Path to the RTSTRUCT DICOM file.

    Returns:
        Dict[str, Dict[str, Any]]: Dictionary containing structures with their contours and display information.

    Raises:
        ValueError: If the file is not a valid RTSTRUCT DICOM file or required sequences are missing.
    """
    fpath = pathlib.Path(fpath)
    try:
        ds = pydicom.dcmread(fpath)
    except pydicom.errors.InvalidDicomError as ide:
        raise ValueError("The provided file is not a valid DICOM file.") from ide
    except Exception as e:
        raise ValueError(f"Error reading RTSTRUCT file: {e}") from e

    if ds.Modality != "RTSTRUCT":
        raise ValueError("File is not an RTSTRUCT DICOM file.")

    required_sequences = ["StructureSetROISequence", "ROIContourSequence"]
    for seq in required_sequences:
        if not hasattr(ds, seq):
            raise ValueError(f"RTSTRUCT file is missing the required {seq}.")

    structures = {}
    roi_nums_to_names = {}
    try:
        for roi in ds.StructureSetROISequence:
            roi_num = getattr(roi, "ROINumber", None)
            roi_name = getattr(roi, "ROIName", "Unknown")
            if roi_num is not None:
                roi_nums_to_names[roi_num] = roi_name
            else:
                st.warning("Found ROI without ROINumber. Skipping this ROI.")
    except Exception as e:
        raise ValueError(f"Error processing StructureSetROISequence: {e}") from e

    try:
        for roi_contour in ds.ROIContourSequence:
            if not hasattr(roi_contour, "ContourSequence"):
                continue
            roi_num = getattr(roi_contour, "ReferencedROINumber", None)
            roi_name = roi_nums_to_names.get(roi_num, "Unknown")

            contours = []
            for contour_seq in roi_contour.ContourSequence:
                contour_data = getattr(contour_seq, "ContourData", None)
                if contour_data is None:
                    continue
                try:
                    points = np.array(contour_data, dtype=np.float32).reshape(-1, 3)
                    contours.append(points)
                except Exception as e:
                    st.warning(
                        f"Error reshaping ContourData: {e}. Skipping this contour."
                    )

            if contours:
                try:
                    colour = f"rgb{tuple(int(c) for c in roi_contour.ROIDisplayColor)}"
                except AttributeError:
                    st.warning(
                        f"ROIDisplayColor missing for ROI {roi_name}. Defaulting to gray."
                    )
                    colour = "rgb(128, 128, 128)"
                structures[roi_name] = {
                    "Contours": contours,
                    "Colour": colour,
                    "Number": roi_num,
                }
    except Exception as e:
        raise ValueError(f"Error processing ROIContourSequence: {e}") from e

    if not structures:
        st.warning("No valid structures found in RTSTRUCT file.")

    return structures


def preprocess_contours(
    structures: Dict[str, Dict[str, Any]],
) -> Dict[float, List[Tuple[str, np.ndarray]]]:
    """
    Precompute and map which contours belong to each Z-coordinate.

    Args:
        structures (Dict[str, Dict[str, Any]]): RT structure data.

    Returns:
        Dict[float, List[Tuple[str, np.ndarray]]]: Mapping of Z-coordinate to contours for each structure.
    """
    contour_map = {}
    for structure_name, structure_data in structures.items():
        for contour in structure_data["Contours"]:
            contour_z = contour[:, 2]
            unique_z = np.unique(contour_z)
            for z in unique_z:
                if z not in contour_map:
                    contour_map[z] = []
                contour_map[z].append((structure_name, contour))
    return contour_map


@st.cache_data(show_spinner=True, persist=True)
def load_rt_dose(
    fpath: str | os.PathLike, ct_headers: Sequence[Dict[str, Any]]
) -> Tuple[Dict[int, np.ndarray], str, Dict[int, np.ndarray], Dict[int, np.ndarray]]:
    """
    Load RTDOSE data and map it to CT slices based on Z-coordinate.

    Args:
        fpath (str | os.PathLike): Path to the RTDOSE DICOM file.
        ct_headers (Sequence[Dict[str, Any]]): Sequence of CT slice headers with 'ipp'.

    Returns:
        Tuple[Dict[int, np.ndarray], str, Dict[int, np.ndarray], Dict[int, np.ndarray]]:
            - dose_map: Mapping of slice index to dose array.
            - dose_units: Units of the dose ('GY' or 'CGY').
            - dose_X: Mapping of slice index to X coordinates arrays.
            - dose_Y: Mapping of slice index to Y coordinates arrays.

    Raises:
        ValueError: If the file is not a valid RTDOSE DICOM file or required attributes are missing.
    """
    fpath = pathlib.Path(fpath)
    try:
        ds = pydicom.dcmread(fpath)
    except pydicom.errors.InvalidDicomError as ide:
        raise ValueError("The provided RTDOSE file is not a valid DICOM file.") from ide
    except Exception as e:
        raise ValueError(f"Error reading RTDOSE file: {e}") from e

    if ds.Modality != "RTDOSE":
        raise ValueError("File is not an RTDOSE DICOM file.")

    dose_grid_scaling = float(getattr(ds, "DoseGridScaling", 1.0))
    if "DoseGridScaling" not in ds:
        st.warning("DoseGridScaling missing. Assuming a scaling factor of 1.0.")

    dose_units = getattr(ds, "DoseUnits", "UNKNOWN")  # Typically 'GY' or 'CGY'

    try:
        dose_data = ds.pixel_array.astype(np.float32) * dose_grid_scaling
    except Exception as e:
        raise ValueError(f"Error processing dose pixel data: {e}") from e

    # Extract dose grid information
    grid_frame_offset_vector = getattr(
        ds, "GridFrameOffsetVector", None
    )  # Z-offsets for each dose slice
    if grid_frame_offset_vector is None:
        st.warning(
            "GridFrameOffsetVector missing. Assuming single dose slice at origin."
        )
        grid_frame_offset_vector = [0.0]

    dose_origin = getattr(ds, "ImagePositionPatient", None)
    if dose_origin is None:
        raise ValueError("Dose ImagePositionPatient missing.")

    dose_origin_np = np.array(dose_origin, dtype=np.float32)

    # Compute dose slice positions based on grid_frame_offset_vector
    try:
        dose_z_positions = dose_origin_np[2] + np.array(
            grid_frame_offset_vector, dtype=np.float32
        )
    except Exception as e:
        raise ValueError(f"Error computing dose slice positions: {e}") from e

    slice_z_positions = [header["ipp"][2] for header in ct_headers]

    dose_map = {}  # slice_idx: dose_array
    dose_X = {}  # slice_idx: X coordinates array
    dose_Y = {}  # slice_idx: Y coordinates array

    for idx, dose_z in enumerate(dose_z_positions):
        # Find the closest CT slice based on Z-coordinate
        try:
            closest_slice_idx = int(
                np.argmin(np.abs(np.array(slice_z_positions) - dose_z))
            )
        except Exception as e:
            st.warning(
                f"Error finding closest CT slice for dose slice {idx + 1}: {e}. Skipping."
            )
            continue

        # Check if this dose_z closely matches the CT slice's z-coordinate (within tolerance)
        z_tolerance = 1e-3  # in mm
        if np.abs(slice_z_positions[closest_slice_idx] - dose_z) > z_tolerance:
            st.warning(
                f"Dose slice {idx + 1} at dose_z={dose_z} mm does not closely match any CT slice Z-coordinate. Skipping."
            )
            continue

        # Store dose data without resampling
        if closest_slice_idx not in dose_map:
            dose_map[closest_slice_idx] = dose_data[idx]
        else:
            # If multiple dose slices map to the same CT slice, average them
            dose_map[closest_slice_idx] = (
                dose_map[closest_slice_idx] + dose_data[idx]
            ) / 2

        # Calculate spatial coordinates for the dose slice
        dose_iop = getattr(ds, "ImageOrientationPatient", None)
        dose_pixel_spacing = getattr(ds, "PixelSpacing", None)
        if dose_iop is None or dose_pixel_spacing is None:
            st.warning(
                f"Missing ImageOrientationPatient or PixelSpacing for dose slice {idx + 1}. Cannot compute spatial coordinates."
            )
            continue

        try:
            X_slice, Y_slice = compute_patient_coordinates(
                ds.Rows,
                ds.Columns,
                tuple(ds.ImagePositionPatient),
                tuple(ds.ImageOrientationPatient),
                tuple(ds.PixelSpacing),
            )
            dose_X[closest_slice_idx] = X_slice
            dose_Y[closest_slice_idx] = Y_slice
        except Exception as e:
            st.warning(
                f"Failed to compute spatial coordinates for dose slice {idx + 1}: {e}. Skipping."
            )
            continue

    if not dose_map:
        st.warning("No valid dose slices were mapped to CT slices.")

    return dose_map, dose_units, dose_X, dose_Y


def window_image(img: np.ndarray, ww: float, wl: float) -> np.ndarray:
    """
    Apply window level and window width to the CT image.

    Args:
        img (np.ndarray): CT image slice as a 2D NumPy array.
        ww (float): Window Width.
        wl (float): Window Level.

    Returns:
        np.ndarray: Windowed image as a 2D NumPy array.
    """
    img_min = wl - (ww / 2)
    img_max = wl + (ww / 2)
    return np.clip(img, img_min, img_max)


def create_structure_legend(structures: Dict[str, Dict[str, Any]]) -> str:
    """
    Create an HTML legend for the anatomical structures with their corresponding colors.

    Args:
        structures (Dict[str, Dict[str, Any]]): Dictionary of structures with display information.

    Returns:
        str: HTML string representing the structures legend.
    """
    legend_html = "<h4>Structures Legend</h4><ul>"
    for structure_name, structure_data in structures.items():
        color = structure_data["Colour"]
        # Convert 'rgb(r, g, b)' to individual r, g, b values
        rgb_values = color.replace("rgb(", "").replace(")", "").split(",")
        r, g, b = [int(v.strip()) for v in rgb_values]
        legend_html += (
            f'<li><span style="display:inline-block;width:12px;height:12px;'
            f'background-color:rgb({r},{g},{b});margin-right:6px;"></span>{structure_name}</li>'
        )
    legend_html += "</ul>"
    return legend_html


def initialize_base_figure(
    ct_image: np.memmap,
    ct_headers: Sequence[Dict[str, Any]],
    X: np.ndarray,
    Y: np.ndarray,
    initial_slice_idx: int,
    wl_default: int,
    ww_default: int,
) -> go.Figure:
    """
    Initialize and configure the base Plotly figure for the CT viewer.

    Args:
        ct_image (np.memmap): Memory-mapped array of CT image data.
        ct_headers (Sequence[Dict[str, Any]]): Sequence of CT slice headers with spatial information.
        X (np.ndarray): X coordinates array.
        Y (np.ndarray): Y coordinates array.
        initial_slice_idx (int): Index of the initial CT slice to display.
        wl_default (int): Default Window Level.
        ww_default (int): Default Window Width.

    Returns:
        go.Figure: Configured Plotly figure object.
    """
    slice_image = ct_image[initial_slice_idx, :, :]
    windowed_img = window_image(slice_image, ww_default, wl_default)
    img_min = wl_default - (ww_default / 2)
    img_max = wl_default + (ww_default / 2)

    slice_z = ct_headers[initial_slice_idx]["ipp"][2]

    # Compute heatmap parameters
    x0 = X[0, 0]
    dx = X[0, 1] - X[0, 0]
    y0 = Y[0, 0]
    dy = Y[1, 0] - Y[0, 0]

    fig = go.Figure()
    heatmap = go.Heatmap(
        z=windowed_img,
        colorscale="gray",
        hovertemplate="HU: %{z}<extra></extra>",
        showscale=False,
        x0=x0,
        dx=dx,
        y0=y0,
        dy=dy,
        zmin=img_min,
        zmax=img_max,
    )
    fig.add_trace(heatmap)

    # Update layout settings
    fig.update_layout(
        title=f"Z = {slice_z:.2f} mm (Slice {initial_slice_idx})",
        margin=dict(l=10, r=10, b=10, t=40),
        height=800,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    # Set fixed aspect ratio for axes
    fig.update_xaxes(
        range=[x0, x0 + dx * ct_image.shape[2]],
        scaleanchor="y",
        scaleratio=1,
        showgrid=False,
        zeroline=True,
        showline=True,
        linecolor="black",
        linewidth=1,
    )
    fig.update_yaxes(
        range=[y0 + dy * ct_image.shape[1], y0],
        autorange=False,
        showgrid=False,
        zeroline=True,
        showline=True,
        linecolor="black",
        linewidth=1,
    )

    return fig


def update_figure(
    fig: go.Figure,
    ct_image: np.memmap,
    slice_idx: int,
    wl: float,
    ww: float,
    ct_headers: Sequence[Dict[str, Any]],
    structures: Dict[str, Dict[str, Any]],
    contour_map: Dict[float, List[Tuple[str, np.ndarray]]],
    selected_structures: Sequence[str],
    dose_map: Dict[int, np.ndarray],
    show_dose: bool,
    dose_units: str,
    dose_X: Dict[int, np.ndarray],
    dose_Y: Dict[int, np.ndarray],
) -> go.Figure:
    """
    Update the existing Plotly figure with new data based on user inputs.

    Args:
        fig (go.Figure): Existing Plotly figure object.
        ct_image (np.memmap): Memory-mapped array of CT image data.
        slice_idx (int): Index of the CT slice to display.
        wl (float): Window Level.
        ww (float): Window Width.
        ct_headers (Sequence[Dict[str, Any]]): Sequence of CT slice headers with spatial information.
        structures (Dict[str, Dict[str, Any]]): Dictionary of anatomical structures.
        contour_map (Dict[float, List[Tuple[str, np.ndarray]]]): Mapping of Z-coordinate to contours.
        selected_structures (Sequence[str]): Sequence of structures selected by the user for display.
        dose_map (Dict[int, np.ndarray]): Mapping of slice index to dose array.
        show_dose (bool): Flag indicating whether to display dose colorwash.
        dose_units (str): Units of the dose ('GY' or 'CGY').
        dose_X (Dict[int, np.ndarray]): Mapping of slice index to X coordinates arrays.
        dose_Y (Dict[int, np.ndarray]): Mapping of slice index to Y coordinates arrays.

    Returns:
        go.Figure: Updated Plotly figure object.
    """
    try:
        slice_image = ct_image[slice_idx, :, :]
        windowed_img = window_image(slice_image, ww, wl)
        img_min = wl - (ww / 2)
        img_max = wl + (ww / 2)
    except IndexError:
        st.error(f"Slice index {slice_idx} is out of bounds.")
        return fig
    except Exception as e:
        st.error(f"Error processing slice {slice_idx}: {e}")
        return fig

    # Update heatmap trace (CT image)
    try:
        fig.data[0].z = windowed_img
        fig.data[0].zmin = img_min
        fig.data[0].zmax = img_max
    except IndexError:
        st.error("CT image heatmap trace is missing.")
        return fig
    except Exception as e:
        st.error(f"Error updating heatmap: {e}")
        return fig

    # Update the title
    try:
        slice_z = ct_headers[slice_idx]["ipp"][2]
        fig.update_layout(title=f"Z = {slice_z:.2f} mm (Slice {slice_idx})")
    except IndexError:
        st.error(f"Slice header for index {slice_idx} is missing.")
    except Exception as e:
        st.error(f"Error updating title: {e}")

    # Remove existing contour and dose overlay traces
    try:
        fig.data = tuple(
            trace
            for trace in fig.data
            if not (
                (isinstance(trace, go.Scatter) and trace.name in structures.keys())
                or (isinstance(trace, go.Heatmap) and trace.name == "Dose Overlay")
            )
        )
    except Exception as e:
        st.error(f"Error removing old traces: {e}")

    # Add new contour traces for the selected structures
    try:
        for structure_name in selected_structures:
            contours = [
                contour
                for (s, contour) in contour_map.get(slice_z, [])
                if s == structure_name
            ]
            if not contours:
                continue

            x = []
            y = []
            for contour in contours:
                x.extend(contour[:, 0].tolist())
                y.extend(contour[:, 1].tolist())
                x.append(None)  # Break between contours
                y.append(None)

            colour = structures[structure_name]["Colour"]
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    line=dict(color=colour, width=2),
                    name=structure_name,
                    showlegend=False,  # Legend is handled within checkboxes
                    hoverinfo="skip",
                )
            )
    except Exception as e:
        st.error(f"Error adding contour traces: {e}")

    # Add RTDOSE overlay if enabled
    if show_dose and slice_idx in dose_map:
        try:
            dose_slice = dose_map[slice_idx]
            dose_X_slice = dose_X.get(slice_idx)
            dose_Y_slice = dose_Y.get(slice_idx)

            if dose_X_slice is not None and dose_Y_slice is not None:
                # Ensure dose_X_slice and dose_Y_slice are Numpy arrays with float32 dtype
                dose_X_slice = dose_X_slice.astype(np.float32)
                dose_Y_slice = dose_Y_slice.astype(np.float32)

                # Normalize dose using Numpy's efficient operations
                dose_min = float(dose_slice.min())
                dose_max = float(dose_slice.max())
                if dose_max > dose_min:
                    normalized_dose = np.clip(
                        (dose_slice - dose_min) / (dose_max - dose_min), 0, 1
                    )
                else:
                    normalized_dose = dose_slice

                # Use Numpy's array operations to prepare data for Plotly
                dose_heatmap = go.Heatmap(
                    z=normalized_dose,
                    colorscale="Jet",
                    opacity=0.5,
                    showscale=False,
                    x0=dose_X_slice[0, 0],
                    dx=dose_X_slice[0, 1] - dose_X_slice[0, 0],
                    y0=dose_Y_slice[0, 0],
                    dy=dose_Y_slice[1, 0] - dose_Y_slice[0, 0],
                    hovertemplate=f"Dose: %{{z:.4f}} {dose_units}<extra></extra>",
                    name="Dose Overlay",
                )
                fig.add_trace(dose_heatmap)
            else:
                st.warning(
                    f"No spatial coordinates found for dose slice at index {slice_idx}. "
                    "Cannot overlay dose data."
                )
        except Exception as e:
            st.error(f"Error adding RTDOSE overlay: {e}")

    return fig


# Sidebar to input DICOM directory, RTSTRUCT file, and RTDOSE file
st.sidebar.header("Input Files")

dicom_dir = st.sidebar.text_input("Enter DICOM directory path")
rtstruct_file = st.sidebar.text_input("Enter RTSTRUCT file path")
rtdose_file = st.sidebar.text_input("Enter RTDOSE file path (optional)")

# Checkbox to toggle RTDOSE colorwash
show_dose = False
if rtdose_file:
    show_dose = st.sidebar.checkbox("Show Dose Colorwash", value=False)

if dicom_dir and rtstruct_file:
    dicom_path = pathlib.Path(dicom_dir)
    rtstruct_path = pathlib.Path(rtstruct_file)
    if dicom_path.exists():
        if rtstruct_path.exists():
            try:
                (
                    ct_image,
                    ct_headers,
                    X,
                    Y,
                    pixel_min,
                    pixel_max,
                    wl_default,
                    ww_default,
                ) = load_ct_as_memmap(dicom_path)
                #                st.write("Successfully Loaded CT as memmap")
                structures = load_rt_structures(rtstruct_path)
                #                st.write("Successfully loaded RT SS")
                contour_map = preprocess_contours(structures)
                st.sidebar.success("CT and RTSTRUCT files loaded successfully.")
            except Exception as e:
                st.error(f"Error loading CT or RTSTRUCT data: {e}")
                st.stop()
        else:
            st.error("RTSTRUCT file path does not exist.")
            st.stop()
    else:
        st.error("DICOM directory path does not exist.")
        st.stop()
else:
    st.info("Please enter both DICOM directory and RTSTRUCT file paths.")
    st.stop()

# Extract Z-coordinates from CT headers
z_coords = [header["ipp"][2] for header in ct_headers]

# Load RTDOSE if provided and path exists
dose_map = {}
dose_units = ""
dose_X = {}
dose_Y = {}
if rtdose_file:
    rtdose_path = pathlib.Path(rtdose_file)
    if rtdose_path.exists():
        try:
            dose_map, dose_units, dose_X, dose_Y = load_rt_dose(
                rtdose_path, ct_headers=ct_headers
            )
            st.sidebar.success("RTDOSE loaded successfully.")
        except Exception as e:
            st.sidebar.error(f"Error loading RTDOSE: {e}")
            dose_map = {}
            dose_units = ""
            dose_X = {}
            dose_Y = {}
    else:
        st.sidebar.error("Invalid RTDOSE file path.")

num_slices = ct_image.shape[0]
height = ct_image.shape[1]
width = ct_image.shape[2]

# Sidebar controls for dynamic updates
with st.sidebar:
    st.header("Controls")

    # Slider to select slice index
    slice_idx = st.slider(
        "Slice Index",
        min_value=0,
        max_value=num_slices - 1,
        value=num_slices // 2,
        step=1,
        key="slice_slider",
    )

    # Display Z-coordinate based on selected slice
    try:
        st.write(f"**Z-Coordinate:** {z_coords[slice_idx]:.2f} mm (Slice {slice_idx})")
    except IndexError:
        st.error(f"Slice index {slice_idx} is out of bounds.")
    except Exception as e:
        st.error(f"Error displaying Z-coordinate: {e}")

    # Sliders for window level and width
    wl = st.slider(
        "Window Level (WL)",
        min_value=int(pixel_min),
        max_value=int(pixel_max),
        value=wl_default,
    )
    ww = st.slider(
        "Window Width (WW)",
        min_value=1,
        max_value=int(pixel_max - pixel_min),
        value=ww_default,
    )

    # Add checkboxes for each structure to toggle visibility with color indicators
    st.markdown("---")
    st.subheader("Toggle Structures")
    selected_structures = []
    for structure_name, structure_data in structures.items():
        # Create two columns: one for color box, one for checkbox
        col1, col2 = st.columns([1, 4])
        with col1:
            color = structure_data["Colour"]
            # Create a colored square using HTML and CSS
            st.markdown(
                f"""
                <div style="
                    width: 20px;
                    height: 20px;
                    background-color: {color};
                    border: 1px solid #000;
                    border-radius: 3px;
                "></div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            # Checkbox with the structure name
            if st.checkbox(structure_name, value=True, key=structure_name):
                selected_structures.append(structure_name)

    # Removed separate legend as colors are now integrated with checkboxes
    st.markdown("---")

# Initialize the figure once
if "base_figure" not in st.session_state:
    try:
        initial_slice_idx = num_slices // 2
        base_fig = initialize_base_figure(
            ct_image,
            ct_headers,
            X,
            Y,
            initial_slice_idx,
            wl_default,
            ww_default,
        )
        st.session_state.base_figure = base_fig
    except Exception as e:
        st.error(f"Error initializing base figure: {e}")
        st.stop()

# Update the figure based on user inputs, including selected structures and dose
updated_fig = update_figure(
    st.session_state.base_figure,
    ct_image,
    slice_idx,
    wl,
    ww,
    ct_headers,
    structures,
    contour_map,
    selected_structures,  # Pass the selected structures to the update function
    dose_map,
    show_dose,
    dose_units,
    dose_X,
    dose_Y,
)

# Display the updated figure
st.plotly_chart(updated_fig, use_container_width=True, height=800)
