import json
import os
import pathlib
import subprocess
from typing import Optional

import anthropic
import github
import pytest

import pymedphys._utilities.test as pmp_test_utils
from pymedphys._claude import githubassist

# Constants
TEST_CONFIG = {
    "owner_repo_name": "pymedphys/pymedphys",
    "issue_number": 1844,
    "test_username": "@!Claude_test",
    "test_comment": "This is a test comment",
    "claude_model": "claude-3-haiku-20240307",
    "max_tokens": 10,
}

HERE = pathlib.Path(__file__).parent.resolve()
BASELINES_JSON = HERE / "baselines.json"


@pytest.fixture
def claude_connection():
    return anthropic.Anthropic()


@pytest.fixture
def github_connection():
    return githubassist.github_client()


@pytest.fixture
def repo(github_connection):
    return github_connection.get_repo(TEST_CONFIG["owner_repo_name"])


@pytest.fixture
def issue(repo):
    return repo.get_issue(TEST_CONFIG["issue_number"])


def test_system_prompt_github_issue_comment(
    repo: github.Repository.Repository, save_baseline: bool = False
) -> None:
    """Test the generation of system prompt for GitHub issue comments.

    Args:
        repo: The GitHub repository fixture
        save_baseline: Whether to save the baseline or compare against it
    """
    system_prompt = githubassist.system_prompt_github_issue_comment(
        repo, TEST_CONFIG["issue_number"]
    )
    assert system_prompt != ""

    if save_baseline:
        json_dict = {"system_prompt": system_prompt}
        BASELINES_JSON.write_text(json.dumps(json_dict, indent=2), encoding="UTF-8")
    else:
        json_dict = json.loads(BASELINES_JSON.read_text(encoding="UTF-8"))
        assert json_dict["system_prompt"] == system_prompt


def test_create_issue_comment_with_claude_response_to_user_comment(
    issue: github.Issue.Issue,
) -> None:
    """Test creating an issue comment with Claude's response.

    Args:
        issue: The GitHub issue fixture
    """
    comment_new: Optional[github.IssueComment.IssueComment] = None

    claude_response_mock = anthropic.types.message.Message(
        id="1234",
        content=[{"text": "This is a\nmultiline\ntest\nresponse.", "type": "text"}],
        model="claude-3-opus-20240229",
        role="assistant",
        type="message",
        usage={"input_tokens": 10, "output_tokens": 25},
    )

    try:
        comment_new = (
            githubassist.create_issue_comment_with_claude_response_to_user_comment(
                issue=issue,
                username=TEST_CONFIG["test_username"],
                user_comment=TEST_CONFIG["test_comment"],
                claude_response=claude_response_mock,
            )
        )

        # Verify comment was created
        assert issue.get_comment(comment_new.id) == comment_new

        # Verify comment can be deleted
        with pytest.raises(github.UnknownObjectException):
            comment_new.delete()
            issue.get_comment(comment_new.id)

    finally:
        if comment_new is not None:
            try:
                comment_new.delete()
            except github.UnknownObjectException:
                pass  # Comment was already deleted


def test_response_to_github_issue_comment_cli(issue: github.Issue.Issue) -> None:
    """Test the CLI command for responding to GitHub issue comments.

    Args:
        issue: The GitHub issue fixture
    """
    issue_comment_count_before = issue.comments

    # Create test environment with required tokens
    test_env = os.environ.copy()
    # Only set dummy values if the tokens aren't already in the environment
    if not test_env.get("GITHUB_TOKEN"):
        test_env["GITHUB_TOKEN"] = "dummy_token_for_testing"
    if not test_env.get("ANTHROPIC_API_KEY"):
        test_env["ANTHROPIC_API_KEY"] = "dummy_anthropic_token_for_testing"

    respond_to_issue_comment_cli = pmp_test_utils.get_pymedphys_claude_cli() + [
        "respond-to-issue-comment"
    ]

    respond_to_issue_comment_cmd = [
        *respond_to_issue_comment_cli,
        str(TEST_CONFIG["issue_number"]),
        TEST_CONFIG["test_username"],
        TEST_CONFIG["test_comment"],
        "--repo",
        TEST_CONFIG["owner_repo_name"],
        "--claude_model",
        TEST_CONFIG["claude_model"],
        "--max_tokens",
        str(TEST_CONFIG["max_tokens"]),
    ]

    # Execute command with test environment
    try:
        subprocess.check_call(respond_to_issue_comment_cmd, env=test_env)
        assert issue.comments == issue_comment_count_before + 1
    except subprocess.CalledProcessError as e:
        print(f"Command failed with return code {e.returncode}")
        print(f"Command was: {' '.join(respond_to_issue_comment_cmd)}")
        raise
