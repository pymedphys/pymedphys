import json
import pathlib

import anthropic
import github
import pytest

from pymedphys._claude import githubassist

OWNER_REPO_NAME = "Matthew-Jennings/pymedphys"
ISSUE_NUMER = 2
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


def test_system_prompt_on_comment_mention(repo, save_baseline=False):

    system_prompt = githubassist.system_prompt_on_comment_mention(repo, ISSUE_NUMER)
    assert system_prompt != ""

    if save_baseline:
        json_dict = {"system_prompt": system_prompt}

        with open(BASELINES_JSON, "w", encoding="UTF-8") as f:
            json.dump(json_dict, f, indent=2)
    else:
        with open(BASELINES_JSON, encoding="UTF-8") as f:
            json_dict = json.load(f)
        assert json_dict["system_prompt"] == system_prompt


def test_create_issue_comment_with_claude_response_to_mention(issue):
    comment_mentioned = "Please summarise"

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

    comment_new = githubassist.create_issue_comment_with_claude_response_to_mention(
        issue, comment_mentioned, claude_response_mock
    )

    assert issue.get_comment(comment_new.id) == comment_new

    comment_new.delete()

    with pytest.raises(github.UnknownObjectException):
        issue.get_comment(comment_new.id)


# Add more tests as needed
