# Choose your path

There is no single right way to use PyMedPhys.
Choose the interface that matches how you want to work.

## Fast decision

Use the app layer if you want the least coding and a graphical workflow.

Use the CLI if you want a repeatable command for Task Scheduler, cron, shell
scripts, batch files, or other automation.

Use the Python library if you want to inspect data, build your own analysis,
or combine PyMedPhys with notebooks and clinic-specific code.

## Side-by-side comparison

| Path           | Best when                    | Good for                                                         | Trade-offs                                                                    |
| -------------- | ---------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| App            | You want point-and-click use | guided workflows and interactive review                          | only available for some tasks                                                 |
| CLI            | You want repeatable commands | scheduled jobs, scripts, operational automation                  | less interactive than Python, and not every library feature has a CLI wrapper |
| Python library | You want maximum control     | notebooks, analysis, custom tooling, integration with local code | requires some Python familiarity                                              |

The library is the broadest interface.
The CLI and app layer expose selected workflows.

The current stable app registry includes MetersetMap and pseudonymisation.
There are also additional experimental apps.
After installation, the app layer is launched via `pymedphys gui`.

## Common scenarios

### "I just want to run something that already exists"

Start with the app layer if a matching app exists.
If not, check whether a CLI command already covers your workflow.
This is usually the lowest-effort route.

### "I need a task to run every day or every night"

Start with the CLI.
It is better suited to Task Scheduler, cron, shell scripts, and other
automation.

### "I need to inspect arrays, tables, plots, or intermediate results"

Start with the Python library.
This is the best path for investigation, prototyping, and validation.

### "I know a little Python, but I do not want to build a full application"

Start with the Python library in a notebook or a short script.
You can always move the repeated parts into CLI automation later.

### "My colleagues are less comfortable with code"

Prefer the app layer when it exists for your task.
If you need something repeatable with minimal interaction, consider a small CLI
wrapper around a fixed workflow.

## Practical recommendations

For most individual users on a workstation, install the broad user stack and
start from the library or app layer.

For departments building repeatable workflows, start with the CLI when there is
already a matching command, and use the library when you need a custom workflow
that does not yet exist as a command.

For advanced users, it is normal to mix interfaces.
A common pattern is:

1. explore a workflow in Python
2. turn the repeated parts into a CLI command or scheduled script
3. use an app when the task benefits from interactive review

## Where to go next

If you are still deciding whether PyMedPhys covers your task, go back to
{doc}`What PyMedPhys can do <what-pymedphys-can-do>`.

If you have chosen an interface and need to install it, continue to
{doc}`Installation options <installation-options>`.

If you are ready to install now, go to the
{doc}`Quick Start Guide <quick-start>`.
