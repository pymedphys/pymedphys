# Configuring a Zenodo access token

The `pymedphys zenodo set-token` command saves an access token to the
system keyring for subsequent PyMedPhys use.

## Interactive setup

Run the command without a credential argument:

```console
pymedphys zenodo set-token
```

If `PYMEDPHYS_ZENODO_TOKEN` is not set, the command requests the token using
a hidden terminal prompt. If there is no interactive terminal, or the terminal
cannot disable echo, it exits with an error instead of reading an exposed token.

## Automated setup

Configure `PYMEDPHYS_ZENODO_TOKEN` using your environment's secrets manager
or your CI service's secret-injection mechanism, then run:

```console
pymedphys zenodo set-token
```

The command reads the environment variable without prompting and stores its
value in the system keyring. Avoid placing token values directly in shell
commands, scripts, or CI logs.

## Compatibility and troubleshooting

The command checks sources in this order: an explicitly supplied positional
token, `PYMEDPHYS_ZENODO_TOKEN`, then the hidden prompt. An explicitly supplied
empty token fails rather than falling back to another source. A missing token
in a non-interactive session also fails with a concise CLI error.

The legacy command `pymedphys zenodo set-token TOKEN` still works, but it
can expose the token in shell history or process arguments. Prefer the
argument-free forms above.

If an incorrect token was saved, run the command again with the correct token
to replace the stored value.
