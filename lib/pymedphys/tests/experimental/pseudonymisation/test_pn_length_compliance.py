import pytest

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
    assert len(components) == 5  # PN always has 5 components
    assert len(components[0]) <= 64

    # Test case 2: Two components - first should be max 63 chars to leave room for delimiter
    pn_value = f"{long_name}^{long_name}"
    result = _pseudonymise_PN(pn_value)
    components = result.split("^")
    assert len(components) == 5  # PN always has 5 components

    # First component + delimiter should be <= 64
    assert len(components[0]) <= 63  # Room for the ^ delimiter
    # Second component can be 64 chars if it's effectively the last non-empty
    assert len(components[1]) <= 64

    # Test case 3: All five components populated with long prefix and suffix
    long_prefix = "P" * 100
    long_suffix = "S" * 100
    pn_value = f"{long_name}^{long_name}^{long_name}^{long_prefix}^{long_suffix}"
    result = _pseudonymise_PN(
        pn_value, strip_name_prefix=False, strip_name_suffix=False
    )
    components = result.split("^")
    assert len(components) == 5  # PN always has 5 components

    # First four components should be max 63 chars (room for delimiter)
    assert len(components[0]) <= 63
    assert len(components[1]) <= 63
    assert len(components[2]) <= 63
    assert len(components[3]) <= 63  # Prefix with delimiter
    assert len(components[4]) <= 64  # Last component (suffix), no delimiter after

    # Verify total length per component group (content + delimiter)
    # Check each component explicitly to avoid loops in tests
    assert len(f"{components[0]}^") <= 64
    assert len(f"{components[1]}^") <= 64
    assert len(f"{components[2]}^") <= 64
    assert len(f"{components[3]}^") <= 64
    # Last component has no delimiter


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
    # Check each component explicitly (avoiding loops and conditionals)
    assert len(f"{components[0]}^") <= 64
    assert len(f"{components[1]}^") <= 64
    assert len(f"{components[2]}^") <= 64
    # Last two components might be empty, but still check
    assert components[3] == "" or len(f"{components[3]}^") <= 64
    assert components[4] == "" or len(components[4]) <= 64


@pytest.mark.pydicom
def test_pn_empty_string():
    """Test that entirely empty PN string is handled correctly."""

    # Test with completely empty PN
    pn_value = ""
    result = _pseudonymise_PN(pn_value)
    components = result.split("^")

    # Should have 5 empty components
    assert len(components) == 5
    assert components == ["", "", "", "", ""]


@pytest.mark.pydicom
def test_pseudonymise_PN_nondefault_max_component_length():
    """Test with non-default max_component_length parameter."""
    # Example input with long components
    pn = "FAMILYNAME^GIVENNAME^MIDDLENAME^PREFIX^SUFFIX"
    max_component_length = 32

    result = _pseudonymise_PN(
        pn,
        max_component_length=max_component_length,
        strip_name_prefix=False,
        strip_name_suffix=False,
    )

    # Split the result into components
    components = result.split("^")
    assert len(components) == 5

    # All components except the last non-empty one must be <= max_component_length - 1
    # Since all components are non-empty, components 0-3 need room for delimiter
    assert len(components[0]) <= max_component_length - 1
    assert len(components[1]) <= max_component_length - 1
    assert len(components[2]) <= max_component_length - 1
    assert len(components[3]) <= max_component_length - 1

    # The last component can be up to max_component_length
    assert len(components[4]) <= max_component_length

    # Verify with delimiter included
    assert len(f"{components[0]}^") <= max_component_length
    assert len(f"{components[1]}^") <= max_component_length
    assert len(f"{components[2]}^") <= max_component_length
    assert len(f"{components[3]}^") <= max_component_length
