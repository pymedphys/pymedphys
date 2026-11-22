"""Regression guard for the scope of MetersetMap clinical data caches."""

import ast
from pathlib import Path

import pytest


_METERSETMAP = Path(__file__).resolve().parents[2] / "_streamlit/apps/metersetmap"


def _is_streamlit_data_cache(decorator):
    function = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "cache_data"
        and isinstance(function.value, ast.Name)
        and function.value.id == "st"
    )


@pytest.mark.parametrize(
    "module_name",
    ["_dicom", "_icom", "_mosaiq", "_deliveries", "_trf", "main"],
)
def test_patient_derived_cache_scope_is_session(module_name):
    source = (_METERSETMAP / f"{module_name}.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cached = [
        (node.name, decorator)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
        if _is_streamlit_data_cache(decorator)
    ]

    assert cached, f"{module_name} no longer has cache decorators to check"
    for function_name, decorator in cached:
        assert isinstance(decorator, ast.Call), function_name
        scope = [value.value for value in decorator.keywords if value.arg == "scope"]
        assert len(scope) == 1, function_name
        assert isinstance(scope[0], ast.Constant), function_name
        assert scope[0].value == "session", function_name
