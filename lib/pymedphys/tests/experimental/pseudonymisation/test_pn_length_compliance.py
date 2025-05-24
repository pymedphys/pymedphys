import pytest
from pymedphys._imports import pydicom

from pymedphys._experimental.pseudonymisation.strategy import _pseudonymise_PN


@pytest.mark.pydicom
def test_pn_length_compliance_with_delimiter():
    """Test that PN components respect the 64-char limit INCLUDING delimiter."""
    
    # Test case 1: Long family name only
    long_name = "A" * 100  # Create a name longer than 64 chars
    pn_value = long_name
    result = _pseudonymise_PN(pn_value)
    
    # Since there's only one component, it should be truncated to 64 chars
    components = result.split("^")
    assert len(components[0]) <= 64
    
    # Test case 2: Two components - first should be max 63 chars to leave room for delimiter
    pn_value = f"{long_name}^{long_name}"
    result = _pseudonymise_PN(pn_value)
    components = result.split("^")
    
    # First component + delimiter should be <= 64
    assert len(components[0]) <= 63  # Room for the ^ delimiter
    # Last non-empty component can be 64 chars
    assert len(components[1]) <= 64
    
    # Test case 3: All five components populated
    pn_value = f"{long_name}^{long_name}^{long_name}^Dr^PhD"
    result = _pseudonymise_PN(pn_value, strip_name_prefix=False, strip_name_suffix=False)
    components = result.split("^")
    
    # First three components should be max 63 chars (room for delimiter)
    assert len(components[0]) <= 63
    assert len(components[1]) <= 63
    assert len(components[2]) <= 63
    assert len(components[3]) <= 63  # "Dr" with delimiter
    assert len(components[4]) <= 64  # Last component, no delimiter after
    
    # Verify total length per component group (content + delimiter)
    for i in range(len(components) - 1):
        # Each component + its delimiter should be <= 64
        component_with_delimiter = components[i] + "^"
        assert len(component_with_delimiter) <= 64, f"Component {i} with delimiter exceeds 64 chars"


@pytest.mark.pydicom
def test_pn_empty_components():
    """Test that empty components are handled correctly."""
    
    # Test with some empty components
    pn_value = "Smith^^John"
    result = _pseudonymise_PN(pn_value)
    components = result.split("^")
    
    # Should have 5 components (family, given, middle, prefix, suffix)
    assert len(components) == 5
    
    # Family name should be pseudonymised and limited
    assert components[0] != "Smith"
    assert len(components[0]) <= 63  # Has subsequent components
    
    # Middle component should be empty
    assert components[1] == ""
    
    # Given name should be pseudonymised
    assert components[2] != "John"
    
    # Last two should be empty (stripped by default)
    assert components[3] == ""
    assert components[4] == ""


@pytest.mark.pydicom
def test_pn_real_world_example():
    """Test with a realistic PersonName that might appear in DICOM."""
    
    # Create a name that would cause issues with the old implementation
    # Each part is exactly 64 chars, which would become 65 with delimiter
    family = "A" * 64
    given = "B" * 64
    middle = "C" * 64
    
    pn_value = f"{family}^{given}^{middle}"
    result = _pseudonymise_PN(pn_value)
    
    # Parse the result
    components = result.split("^")
    
    # Verify each component + delimiter doesn't exceed 64
    assert len(components[0]) <= 63  # Family has subsequent components
    assert len(components[1]) <= 63  # Given has subsequent components
    assert len(components[2]) <= 64  # Middle might be last non-empty
    
    # Verify the DICOM standard compliance
    # "The Value Length of each component group is 64 characters maximum, 
    # including the delimiter for the component group"
    if len(components) > 1:
        for i in range(len(components) - 1):
            if components[i]:  # Only check non-empty components
                assert len(components[i] + "^") <= 64