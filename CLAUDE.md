# CLAUDE.md

Before working in this repository, read and follow [`AGENTS.md`](AGENTS.md).
It contains the shared development commands, architecture, implementation
conventions, and workflow rules for all coding agents. The instructions below
are additional requirements specific to Claude Code.

## Claude Code Workflow Guidelines

### The `@claude` Workflow

`.github/workflows/claude.yml` runs `anthropics/claude-code-action` when an owner, member, or collaborator of the repository mentions `@claude` in an issue, comment, or review. The workflow checks the author's association with the repository, and the action checks that the triggering user has write access. Its GitHub token covers contents, issues, and pull requests only.

- Set the model and any extra tools through `claude_args` (`--model`, `--allowedTools`). Version 1 of the action ignores the old `model` and `allowed_tools` inputs.
- The workflow adds no tools to the action's defaults: reading, searching, and editing files in the workspace, and committing and pushing through the action's own `git add`, `git commit`, `git rm`, and push wrapper. It cannot run tests or other repository code; CI tests every commit it pushes. When a change needs `uv lock` or `pymedphys dev propagate`, say so in the reply instead of editing the generated files by hand.
- Do not widen the workflow's tools or token permissions without the maintainers' agreement, and propose any widening in a pull request of its own, never as part of another change. Say which command or permission is needed and why.
- Never allow commands that run repository code or build hooks, such as `uv run`, `uv sync`, `uv lock`, tests, or linters. The action checks out the head of a pull request from a fork, and the job holds the API key and a repository write token, so such a command would run an outside contributor's code with them.
- Never allow `git push`, which bypasses the push wrapper's checks, or commands that switch, merge, or reset branches, which the action manages itself.
- Keep workflow write off, as the maintainers decided: never add `workflows: write` to `additional_permissions` or pass the action a token that has it. With it, a prompt-injected run could push a workflow change that then runs with the repository's secrets.
- An `--allowedTools` entry ending in `:*` matches that command prefix; any other entry matches only that exact command. A command chained with `&&` or `;` runs only if every part is allowed. Run commands one at a time and check each result instead of chaining them, which puts security before efficiency.
- A run can start from the repository state just before a recent merge, so a permission that merge added may not apply to it yet.

### Workflow Files

GitHub accepts a push that creates or changes a file in `.github/workflows/` only from a token with the `workflows` permission. Claude Code sessions directed by a maintainer can normally push workflow changes, so edit `.github/workflows/` directly. The `@claude` workflow cannot, and its permission stays off (see "The `@claude` Workflow").

When a push is rejected for lacking the `workflows` permission:

1. Commit the workflow as `claude_created_workflows_preview/<name>.yml`, under the name it will have in `.github/workflows/`, and push it to the pull request's branch.
2. Ask a maintainer to move it within that pull request, and give the command for both bash and PowerShell, where `mv` is `Move-Item` and refuses to overwrite an existing file unless `-Force` is passed:
   - bash: `mv claude_created_workflows_preview/x.yml .github/workflows/x.yml`
   - PowerShell: `Move-Item -Force claude_created_workflows_preview/x.yml .github/workflows/x.yml`
3. If that commit also fails, post the complete file in a pull request
   comment inside a collapsed `<details>` block, say why it could not be
   committed, and say where it belongs.

The staged file must pass the same workflow checks as one in place (see [Security Scanning Policy](AGENTS.md#security-scanning-policy)). The move is complete when the file is in `.github/workflows/`, `claude_created_workflows_preview/` no longer holds it, and the pull request's checks pass.
