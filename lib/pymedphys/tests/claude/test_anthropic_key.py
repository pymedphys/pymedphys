import os
import warnings

import anthropic
import pytest


# Custom pytest plugin to improve error output
def pytest_configure(config):
    """Add a custom hook to improve error messages without requiring -v"""
    config.addinivalue_line(
        "markers", "anthropic_key: mark tests that require an Anthropic API key"
    )


# Add to your conftest.py if you have multiple test files


@pytest.mark.anthropic_key
def test_anthropic_api_key(capsys):
    """Test that the Anthropic API key is valid and working properly.

    Uses capsys fixture to capture and display stdout even without -v flag.
    """
    # Get API key from environment variable
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    # Skip the test if no API key is provided
    if not api_key:
        warnings.warn(
            "ANTHROPIC_API_KEY environment variable not set. "
            "This test will likely fail. Set this variable to run API tests.",
            UserWarning,
        )
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")

    # Initialize the client
    client = anthropic.Anthropic(api_key=api_key)

    # Test with a simple message
    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=10,
        messages=[{"role": "user", "content": "Say hello in exactly 5 words"}],
    )

    # Verify we got a response with better error messages
    response_text = None
    try:
        assert message is not None, "API returned no message"
        assert message.content is not None, "Message contains no content"
        assert len(message.content) > 0, "Message content array is empty"
        assert isinstance(
            message.content[0].text, str
        ), "Message content is not a string"

        # Get the actual text for display
        response_text = message.content[0].text
        print(f"\nAPI Response: '{response_text}'")

        # Optional: Check if the response has approximately 5 words
        # This is not perfect as Claude might not always follow the exact instruction
        word_count = len(response_text.split())
        assert 4 <= word_count <= 6, f"Expected approximately 5 words, got {word_count}"
    except Exception as e:
        if response_text:
            pytest.fail(f"{str(e)} - Response was: '{response_text}'")
        else:
            pytest.fail(str(e))


# Optional: Add a parametrized test for multiple models
@pytest.mark.anthropic_key
@pytest.mark.parametrize(
    "model_name",
    [
        "claude-3-haiku-20240307",
        "claude-3-5-sonnet-20241022",  # Add or remove models as needed
    ],
)
def test_anthropic_models(model_name: str, capsys):
    """Test that specific Anthropic models are accessible with the API key."""
    # Get API key from environment variable
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    # Skip the test if no API key is provided
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")

    # Initialize the client
    client = anthropic.Anthropic(api_key=api_key)

    # Test with a simple message
    try:
        print(f"\nTesting model: {model_name}")
        message = client.messages.create(
            model=model_name, max_tokens=5, messages=[{"role": "user", "content": "Hi"}]
        )
        # If we get here, the model is accessible
        assert message is not None
        response_text = (
            message.content[0].text if message.content else "No text in response"
        )
        print(f"Model response: '{response_text}'")
    except anthropic.APIError as e:
        error_msg = str(e)
        # If the error is about model access, we'll fail the test with useful information
        if "model" in error_msg.lower() and "access" in error_msg.lower():
            pytest.fail(f"No access to model {model_name}: {error_msg}")
        else:
            # For other API errors, provide more context
            pytest.fail(f"API error when testing {model_name}: {error_msg}")
