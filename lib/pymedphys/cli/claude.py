# Copyright (C) 2024 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provides a set of tools for interacting with GitHub using Anthropic's Claude.
"""
import os

from pymedphys._claude.githubassist import respond_to_issue_comment_cli


def set_up_claude_cli(subparsers):
    claude_parser = subparsers.add_parser(
        "claude", help="An AI toolbox for interacting with GitHub issues."
    )
    claude_subparsers = claude_parser.add_subparsers(dest="claude")

    respond_to_issue_comment(claude_subparsers)

    return claude_parser, claude_subparsers


def claude_cli(subparsers):
    claude_parser, _ = set_up_claude_cli(subparsers)

    return claude_parser


def respond_to_issue_comment(claude_subparsers):
    parser = claude_subparsers.add_parser(
        "respond-to-issue-comment",
        help="Respond to a GitHub issue comment with a message from Claude.",
    )
    parser.add_argument(
        "issue_number",
        type=int,
        help="The number of the issue on the Github repository. ",
    )

    parser.add_argument(
        "username",
        type=str,
        help="The author of the text to include in the user prompt to Claude.",
    )

    parser.add_argument(
        "user_comment",
        type=str,
        help="The text to include in the user prompt to Claude.",
    )

    parser.add_argument(
        "--repo",
        "-r",
        default="pymedphys/pymedphys",
        type=str,
        help=(
            "The Github repository including its organisation. "
            "Defaults to 'pymedphys/pymedphys'"
        ),
    )

    parser.add_argument(
        "--github-token",
        "-g",
        default=os.environ.get("GITHUB_TOKEN"),
        type=str,
        help=(
            "The access token to use the GitHub REST API for this repo. "
            "Note that the token must have sufficient privileges to "
            "readand write to the repo's issues"
        ),
    )

    parser.add_argument(
        "--anthropic_api_key",
        "-a",
        default=os.environ.get("ANTHROPIC_API_TOKEN"),
        type=str,
        help="The access key to use the Anthropic API.",
    )

    parser.add_argument(
        "--claude_model",
        "-m",
        default="claude-3-opus-20240229",
        type=str,
        help="The access key to use the Anthropic API.",
    )

    parser.add_argument(
        "--max_tokens",
        "-t",
        default=1024,
        type=int,
        help="The access key to use the Anthropic API.",
    )

    parser.set_defaults(func=respond_to_issue_comment_cli)
