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


def system_prompt_github_issue_comment(
    repo: github.Repository.Repository, issue_number: int
) -> str:
    """Construct a system prompt for Claude based on the details of a GitHub issue.

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

    system_prompt = (
        "You are the AI assistant, 'Claude', providing support on a "
        f"GitHub Issue in the {repo.name} repository. The issue title "
        f"'{issue.title}' and the issue number is {issue_number}. The "
        "issue description is enclosed in the <issue_description> XML "
        "tags below. All subsequent comments are enclosed in the "
        "<issue_comments> XML tags below. Please be helpful and "
        "supportive.\n"
        f"<issue_description>{issue.body}</issue_description>\n"
        f"<issue_comments>{comments}</issue_comments>"
    )

    return system_prompt


def user_prompt_from_issue_comment(username: str, user_comment: str) -> str:
    """Construct a user prompt for Claude based on the details of an issue.

    Args:
        issue (dict): A dictionary containing the details of the issue.

    Returns:
        str: The user prompt for Claude.
    """

    user_prompt = (
        f"Please respond to the comment by {username}. This comment is "
        "provided in the <comment> XML tags below.\n"
        f"<comment>{user_comment}</comment>"
    )
    return user_prompt


def create_issue_comment_with_claude_response_to_user_comment(
    issue: github.Issue.Issue,
    username: str,
    user_comment: str,
    claude_response: anthropic.types.message.Message,
    claude_system_prompt_link=None,
) -> github.IssueComment.IssueComment:
    """Create a comment on a GitHub issue.

    Args:
        issue (github.Issue.Issue): The issue to comment on.
        user_comment (str): The comment that mentioned Claude.
        claude_response (str): The response from Claude.
        claude_system_prompt_link (str, optional): The link to the system prompt (e.g.,
            in the CI). Defaults to None.
    """
    if claude_system_prompt_link is None:
        claude_system_prompt_link = "N/A"

    if hasattr(claude_response, "error"):
        claude_response_text = claude_response.error.message

    else:
        claude_response_text = claude_response.content[0].text

    comment_body_new = (
        "**AI Assistant Claude**\n\n"
        "*Prompt sent to Claude:* "
        f"[link]({claude_system_prompt_link})\n\n"
        f"*Comment that called Claude:*\n"
        f"> **{username}**: {user_comment}\n"
        "*Claude's response:*\n\n"
        f"{claude_response_text}"
    )
    return issue.create_comment(comment_body_new)


def respond_to_issue_comment_cli(args):
    logging.info("Initialising GitHub client...")
    g = github_client(token=args.github_token)

    logging.info("Initialising Claude client...")
    claude_client = anthropic.Anthropic(api_key=args.anthropic_api_key)

    logging.info("Getting repo %s...", args.repo)
    repo = g.get_repo(args.repo)

    logging.info("Creating system prompt for Claude...")
    system_prompt = system_prompt_github_issue_comment(repo, args.issue_number)

    logging.info("Creating user prompt for Claude...")
    user_prompt = user_prompt_from_issue_comment(args.username, args.user_comment)

    logging.info("Sending message to Claude and obtaining response...")
    claude_response = claude_client.messages.create(
        model=args.claude_model,
        max_tokens=args.max_tokens,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": user_prompt,
            }
        ],
    )

    logging.info("Creating comment on %s issue %i", args.repo, args.issue_number)
    create_issue_comment_with_claude_response_to_user_comment(
        issue=repo.get_issue(args.issue_number),
        user_comment=args.user_comment,
        claude_response=claude_response,
    )
