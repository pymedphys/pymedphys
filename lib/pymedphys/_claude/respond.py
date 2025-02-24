# Copyright (C) 2024 Matthew Jennings and contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Implementation of Claude-based response functionality for GitHub issues."""

import logging

import anthropic

from pymedphys._claude import githubassist


def respond_to_issue_comment_cli(args) -> None:
    """CLI entry point for responding to GitHub issues with Claude.

    Args:
        args: The parsed command line arguments.
    """
    logging.info("Initialising GitHub client...")
    g = githubassist.github_client(token=args.github_token)

    logging.info("Getting repo %s...", args.repo)
    repo = g.get_repo(args.repo)

    logging.info("Creating system prompt for Claude...")
    system_prompt = githubassist.system_prompt_github_issue_comment(
        repo, args.issue_number
    )

    logging.info("Creating user prompt for Claude...")
    user_prompt = githubassist.user_prompt_from_issue_comment(
        args.username, args.user_comment
    )

    logging.info("Initialising Claude client...")
    claude_client = anthropic.Anthropic(api_key=args.anthropic_api_key)

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
    githubassist.create_issue_comment_with_claude_response_to_user_comment(
        issue=repo.get_issue(args.issue_number),
        username=args.username,
        user_comment=args.user_comment,
        claude_response=claude_response,
    )
