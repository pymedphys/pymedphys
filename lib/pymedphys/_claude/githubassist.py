import logging
import os

import anthropic
import github

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s - %(levelname)s - %(message)s",
)


def github_client(token=None) -> github.Github:
    """Get an instance of the GitHub API client.

    Args:
        token (str, optional): The API key to use for authentication.
            If none is supplied, the key will be read from the
            GITHUB_REST_API_TOKEN environment variable. Defaults to None.

    Returns:
        github.Github: An instance of the GitHub API client.
    """

    if token is None:
        token = os.environ.get("GITHUB_TOKEN")

    auth = github.Auth.Token(token=token)

    return github.Github(auth=auth)


def system_prompt_on_comment_mention(
    repo: github.Repository.Repository, issue_number: int
) -> str:
    """Construct a system prompt for Claude based on the details of an issue.

    Args:
        repo (github.Repository.Repository): The repository containing the issue.
        issue_number (int): The number of the issue.

    Returns:
        str: The system prompt for Claude.
    """

    issue = repo.get_issue(issue_number)
    comments = [
        {
            "username": comment.user.login,
            "text": comment.body,
        }
        for comment in issue.get_comments()
    ]

    system_prompt = f"""You are the AI assistant, "Claude", providing support on a
    GitHub Issue in the {repo.name} repository. The issue title is '{issue.title}' and
    the issue number is `{issue_number}`. The original issue description is enclosed
    in the <issue_description> XML tags below. All subsequent comments are enclosed in
    the <issue_comments> XML tags below. Please be helpful and supportive.

    <issue_description>{issue.body}</issue_description>
    <issue_comments>{comments}</issue_comments>"""

    return system_prompt


def user_prompt_on_comment_mention(comment_mentioned: str) -> str:
    """Construct a user prompt for Claude based on the details of an issue.

    Args:
        issue (dict): A dictionary containing the details of the issue.

    Returns:
        str: The user prompt for Claude.
    """

    user_prompt = f"""
    Please respond to the latest comment in the conversation that mentions you, Claude.
    This comment is provided in the <comment> XML tags below.

    <comment>
    {comment_mentioned}
    </comment>
    """

    return user_prompt


def create_issue_comment_with_claude_response_to_mention(
    issue: github.Issue.Issue,
    comment_mentioned: str,
    claude_response: anthropic.types.message.Message,
    claude_system_prompt_link=None,
) -> github.IssueComment.IssueComment:
    """Create a comment on a GitHub issue.

    Args:
        issue (github.Issue.Issue): The issue to comment on.
        comment_mentioned (str): The comment that mentioned Claude.
        claude_response (str): The response from Claude.

    """
    if claude_system_prompt_link is None:
        claude_system_prompt_link = "N/A"

    if hasattr(claude_response, "error"):
        claude_response_text = claude_response.error.message

    else:
        claude_response_text = claude_response.content[0].text

    comment_body_new = f"""
    **AI Assistant Claude**

    *Prompt sent to Claude:* [link]({claude_system_prompt_link})

    *Comment that called Claude:*
    > {comment_mentioned}

    *Claude's response:*

    {claude_response_text}"""

    return issue.create_comment(comment_body_new)


if __name__ == "__main__":
    OWNER_REPO_NAME = "Matthew-Jennings/pymedphys"
    ISSUE_NUMBER = 2
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    CALLING_COMMENT = (
        "Please summarise the issue so far and what you think the next steps should be."
    )

    logging.info("Initialising GitHub clients...")
    g = github_client(token=GITHUB_TOKEN)

    logging.info("Initialising Claude client...")
    claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    logging.info("Getting repo %s", OWNER_REPO_NAME)
    repo = g.get_repo(OWNER_REPO_NAME)

    logging.info("Creating system prompt for Claude...")
    system_prompt = system_prompt_on_comment_mention(repo, ISSUE_NUMBER)

    logging.info("Creating user prompt for Claude...")
    user_prompt = user_prompt_on_comment_mention(CALLING_COMMENT)

    logging.info("Calling Claude...")
    claude_response = claude_client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": user_prompt,
            }
        ],
    )

    logging.info("Creating comment on issue %i", ISSUE_NUMBER)
    create_issue_comment_with_claude_response_to_mention(
        issue=repo.get_issue(ISSUE_NUMBER),
        comment_mentioned=CALLING_COMMENT,
        claude_response=claude_response,
    )
