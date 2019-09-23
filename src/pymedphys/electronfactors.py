"""A suite of functions that model electron insert/cutout factors by
parameterising them as equivalent ellipses.
"""


from ._electronfactors import (
    parameterise_insert,
    spline_model,
    calculate_deformability,
    spline_model_with_deformability,
    calculate_percent_prediction_differences,
    visual_alignment_of_equivalent_ellipse,
    convert2_ratio_perim_area,
    create_transformed_mesh,
)
