"""A suite of functions that model electron insert/cutout factors by
parameterising them as equivalent ellipses.
"""

# pylint: disable = unused-import


import apipkg

apipkg.initpkg(
    __name__,
    {
        "calculate_deformability": "._electronfactors:calculate_deformability",
        "calculate_percent_prediction_differences": "._electronfactors:calculate_percent_prediction_differences",
        "convert2_ratio_perim_area": "._electronfactors:convert2_ratio_perim_area",
        "create_transformed_mesh": "._electronfactors:create_transformed_mesh",
        "parameterise_insert": "._electronfactors:parameterise_insert",
        "spline_model": "._electronfactors:spline_model",
        "spline_model_with_deformability": "._electronfactors:spline_model_with_deformability",
        "visual_alignment_of_equivalent_ellipse": "._electronfactors:visual_alignment_of_equivalent_ellipse",
    },
)
