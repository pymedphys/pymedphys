"""A suite of functions that model electron insert/cutout factors by
parameterising them as equivalent ellipses.
"""

# pylint: disable = unused-import

from ._electronfactors import (
    calculate_deformability,
    calculate_percent_prediction_differences,
    convert2_ratio_perim_area,
    create_transformed_mesh,
    parameterise_insert,
    plot_model,
    spline_model,
    spline_model_with_deformability,
    visual_alignment_of_equivalent_ellipse,
)
