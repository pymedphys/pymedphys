# Copyright (C) 2024 Matthew Jennings
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""GitHub utilities for Claude integration."""

import os

import github


def github_client(token=None):
    """Get an instance of the GitHub API client.

    Args:
        token (str, optional): The API key to use for authentication.
            If none is supplied, the key will be read from the
            GITHUB_TOKEN environment variable. Defaults to None.

    Returns:
        github.Github: An instance of the GitHub API client.
    """
    if token is None:
        token = os.environ.get("GITHUB_TOKEN")

    auth = github.Auth.Token(token=token)
    return github.Github(auth=auth)


def system_prompt_github_issue_comment(repo, issue_number: int) -> str:
    """Construct a system prompt for Claude based on the details of a GitHub issue.

    Args:
        repo: The repository containing the issue.
        issue_number: The number of the issue.

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
    """Construct a user prompt for Claude based on a GitHub comment.

    Args:
        username: The username who made the comment.
        user_comment: The content of the comment.

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
    issue,
    username: str,
    user_comment: str,
    claude_response,
    claude_system_prompt_link=None,
):
    """Create a comment on a GitHub issue.

    Args:
        issue: The issue to comment on.
        username: The username who made the comment.
        user_comment: The comment that mentioned Claude.
        claude_response: The response from Claude.
        claude_system_prompt_link: The link to the system prompt (e.g.,
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
        f"*Prompt sent to Claude:* [link]({claude_system_prompt_link})\n\n"
        f"*Comment that called Claude:*\n"
        f"> **{username}**: {user_comment}\n\n"
        "*Claude's response:*\n\n"
        f"{claude_response_text}"
    )
    return issue.create_comment(comment_body_new)
