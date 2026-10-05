# Publish documentation

For contributors previewing pages and maintainers administering hosted builds.

**Prerequisites:** the [shared checkout setup](../start/setup.md), documentation dependencies and approved sample data. Hosted settings require project administration access. **Inputs:** canonical prose, notebooks, docstrings and parser definitions. **Outputs:** HTML and a build log, plus a hosted preview when requested. **Success:** a warnings-as-errors build completes, executable notebook changes run in the intended environment and the affected pages, links and downloads render correctly.

## Local preview and generated sources

From the repository root:

```shell
uv sync --python 3.14 --locked --group docs
uv run pymedphys dev docs
```

Open `lib/pymedphys/docs/_build/html/index.html`, or serve that directory with `uv run python -m http.server --directory lib/pymedphys/docs/_build/html 8000` and visit `http://localhost:8000`. Stop the server after inspection.

`pymedphys dev docs --prep` copies README, CONTRIBUTING and CHANGELOG from their canonical repository sources, renders the de-identification requirements matrix and generates Sphinx configuration. Edit the canonical inputs, never those generated copies. Preparation also obtains the approved dose inputs used by notebooks. The [authoring guide](../guides/authoring.md) provides worked page, notebook and API examples.

The HTML build executes notebooks through Jupyter Book's cache and raises notebook errors. Remove the notebook execution cache when execution inputs or dependencies change and the cache cannot establish their identity; CI's key includes these inputs. `pymedphys dev docs --linkcheck` checks external links without executing notebooks. Inspect each important advisory failure individually, including fragments and downloads.

## GitHub artefacts

The documentation workflow builds HTML with warnings treated as errors and uploads `docs-html`; its separate advisory link checker uploads `docs-linkcheck`. Download and unzip the HTML artefact to inspect it locally. Review the constituent job and current revision: uploads can occur after a build failure. An Actions artefact is a downloadable preview, not a publicly hosted site.

## Read the Docs

Read the Docs builds and hosts
[docs.pymedphys.com](https://docs.pymedphys.com/), outside GitHub Actions. It
reads `.readthedocs.yml` and installs dependencies from the same `uv.lock` as
the `Documentation` workflow, with `uv sync` for the project and the `docs`
dependency group. Read the Docs does not pass `--no-default-groups`, so it also
installs the default `dev` group, which holds every extra and tool, unless
`UV_NO_DEFAULT_GROUPS=1` is set in the project's Read the Docs settings.
GitHub's documentation job explicitly excludes default groups. Read the Docs
runs `pymedphys dev docs --prep` and fails on Sphinx warnings. Automation rules
in its dashboard, not this repository, decide which pushes and pull requests
it builds. With the dashboard configuration below, the behaviour is:

| Event | GitHub Actions | Read the Docs |
|-------|----------------|---------------|
| Pull request | `docs-check` when selected, with the `docs-html` artefact | No build |
| Pull request labelled `rtd-preview` | The same | A hosted preview of each new commit |
| Push to `main` | No documentation build | Builds and publishes `latest` |
| Other branches and tags | No documentation build | Builds active versions |

A Read the Docs status on a pull request is informational and never a
required check. Without the rules below, Read the Docs builds every pull
request, and each build waits for and occupies one of the project's
concurrent build slots. The rules decide before a build exists, so an
unlabelled pull request never enters the queue. Filtering inside the build,
such as a `build.jobs` command that exits with code 183 to cancel it, runs
only once the build has been queued and started, so do not use it to limit
pull request builds.

### Dashboard configuration

A maintainer of the Read the Docs project sets this up once:

1. Connect the project to `pymedphys/pymedphys` through the Read the Docs
   GitHub App. Rules can filter on pull request labels only through it; with
   the older webhook integration, every pull request builds regardless of the
   rules.
2. Under **Settings**, **Pull request builds**, keep **Build pull requests for
   this project** enabled.
3. Under **Settings**, **Automation rules**, add these two rules. Set
   **Version predefined match pattern** to **Any version** and **Action** to
   **Trigger build for version** in both, and leave every field not listed
   here empty:

   | Description | Version types | Webhook labels match pattern |
   |-------------|---------------|------------------------------|
   | Build branches and tags | Branch, Tag | (empty) |
   | Build labelled pull request previews | Pull request | `^rtd-preview$` |

4. Create the `rtd-preview` label in the GitHub repository.

Read the Docs documents that once any rule with this action is enabled, only
events a rule matches trigger builds, so the first rule keeps `main` and tag
builds. It builds only active versions, as Read the Docs does without rules.
Keep its version pattern at **Any version**: rules match the Read the Docs
version name, and the version that tracks `main` is named `latest`, so a
custom pattern such as `^main$` would stop publishing it. Keep the label pattern off the first
rule: pushes carry no labels, so a label pattern there would stop every
branch and tag build. The label pattern is a regular expression that may
match anywhere in a label's name, so keep both anchors.

To confirm the setup, check that a pull request without the label adds
nothing to the project's build list and gets no Read the Docs status, and
that the next merge to `main` builds `latest`.

If the project cannot use the GitHub App, disable **Build pull requests for
this project** instead; hosted previews are then unavailable.

### Requesting a hosted preview

Anyone who can label pull requests (triage access or above) can request a
preview:

1. Add the `rtd-preview` label to the pull request.
2. Push a commit to the pull request. Read the Docs evaluates the rules only
   when a pull request is opened, reopened, or receives commits, so adding
   the label alone does not start a build.
3. Follow the Read the Docs status on the pull request to the preview.

While the label remains, every new commit builds a preview; remove it to
stop. Adding or removing any label also re-runs CI and the security workflow.


## Validate a migration

Follow [documentation ownership and checking](../../project/documentation.md) when retaining URLs and important fragments. Inspect source and HTML relative links, retained section anchors, notebook launches, report bundles, navigation, search and version selection on desktop and narrow screens. [Distribution checks](release.md#verify-packaging-before-a-release) must confirm documents needed at runtime or by installed tests remain packaged.

Recheck this guide whenever `_dev/docs.py`, `_config.yml`, `.readthedocs.yml`, the documentation workflow or hosted dashboard rules change.
