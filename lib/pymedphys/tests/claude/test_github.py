import json
import pathlib
import subprocess

import anthropic
import github
import pytest

import pymedphys._utilities.test as pmp_test_utils
from pymedphys._claude import githubassist

OWNER_REPO_NAME = "pymedphys/pymedphys"
ISSUE_NUMER = 1844
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
    return github_connection.get_repo(OWNER_REPO_NAME)


@pytest.fixture
def issue(repo):
    return repo.get_issue(ISSUE_NUMER)


def test_system_prompt_github_issue_comment(repo, save_baseline=False):
    system_prompt = githubassist.system_prompt_github_issue_comment(repo, ISSUE_NUMER)
    assert system_prompt != ""

    if save_baseline:
        json_dict = {"system_prompt": system_prompt}

        with open(BASELINES_JSON, "w", encoding="UTF-8") as f:
            json.dump(json_dict, f, indent=2)
    else:
        with open(BASELINES_JSON, encoding="UTF-8") as f:
            json_dict = json.load(f)
        assert json_dict["system_prompt"] == system_prompt


def test_create_issue_comment_with_claude_response_to_user_comment(issue):
    username = "@!Claude_test"
    user_comment = "Please summarise"

    claude_response_mock = anthropic.types.message.Message(
        id="1234",
        content=[
            anthropic.types.ContentBlock(
                text="This is a\nmultiline\ntest\nresponse.", type="text"
            )
        ],
        model="claude-3-opus-20240229",
        role="assistant",
        type="message",
        usage=anthropic.types.Usage(input_tokens=10, output_tokens=25),
    )

    comment_new = (
        githubassist.create_issue_comment_with_claude_response_to_user_comment(
            issue, username, user_comment, claude_response_mock
        )
    )
    try:
        assert issue.get_comment(comment_new.id) == comment_new
        with pytest.raises(github.UnknownObjectException):
            comment_new.delete()
            issue.get_comment(comment_new.id)
    finally:
        if comment_new is not None:
            comment_new.delete()


def test_response_to_github_issue_comment_cli(issue):
    issue_comment_count_before = issue.comments

    respond_to_issue_comment_cli = pmp_test_utils.get_pymedphys_dicom_cli() + [
        "respond-to-issue-comment"
    ]

    respond_to_issue_comment_cmd = (
        f"{respond_to_issue_comment_cli} "
        f"{ISSUE_NUMER} "
        f"{OWNER_REPO_NAME} "
        "@!Claude_test "
        "'This is a test comment'"
        "--repo 'pymedphys/pymedphys' "
        "--claude_model claude-3-haiku-20240307"
        "--max_tokens 10"
    )
    try:
        subprocess.check_call(respond_to_issue_comment_cmd)
        assert issue.comments == issue_comment_count_before + 1
    finally:
        remove_file(temp_anon_filepath)
