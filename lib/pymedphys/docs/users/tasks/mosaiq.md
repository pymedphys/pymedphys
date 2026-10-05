# Query Mosaiq

Use `pymedphys.mosaiq.connect` and `execute` for an authorised SQL reporting or
integration workflow. Install `pymedphys[mosaiq]` or `user`. Obtain the hostname,
port, database name, and a database account with the required read permissions.
The default port is 1433 and database is `MOSAIQ`.

## Check connectivity and close the connection

This example contacts your configured server; it does not use an embedded
practice database. Substitute your approved endpoint. The query returns only a
constant, so first establish connectivity before asking for clinical records.

```python
import pymedphys

with pymedphys.mosaiq.connect("mosaiq.example.org") as connection:
    rows = pymedphys.mosaiq.execute(
        connection, "SELECT %(value)s AS documentation_value", {"value": 42}
    )
    assert rows == [(42,)]
    print("Connection and parameterised query succeeded.")
```

The context manager closes the connection on exit, including if the query
raises. `execute` opens/closes a cursor and returns a list of row tuples.
Types reflect the database values; the rows are not all strings. For a connection
kept outside a context manager, call `connection.close()` in a `finally` block.

If neither username nor password is supplied, PyMedPhys reads the operating
system keyring and prompts for missing values, storing the credentials for
later use. Supplying **both** explicitly uses them without storing them;
supplying only one raises `ValueError`. A scheduled job should not depend on
an interactive prompt or another user's keyring. Pass both from your authorised
secret store or provision the service account's credential storage. Keep
credentials out of scripts, reports, and `config.toml`.

The driver requests a read-only connection, but database permissions remain the
control on which operations the account may perform. Use a database account
limited to the intended reporting permissions.

## Make a parameterised report

For an authorised phantom/test record, this example finds internal field IDs
from the database's patient identifier. It is a pattern to adapt to the schema
and intended records at your centre:

```python
import pandas as pd
import pymedphys

query = """
SELECT TxField.FLD_ID, TxField.Field_Label, TxField.Field_Name
FROM TxField
JOIN Ident ON TxField.Pat_ID1 = Ident.Pat_ID1
WHERE Ident.IDA = %(patient_id)s
ORDER BY TxField.FLD_ID
"""
with pymedphys.mosaiq.connect("mosaiq.example.org") as connection:
    rows = pymedphys.mosaiq.execute(
        connection, query, {"patient_id": "YOUR_APPROVED_PHANTOM_ID"}
    )
report = pd.DataFrame(rows, columns=["field_id", "field_label", "field_name"])
print(f"Rows returned: {len(report)}")
```

Use pymssql placeholders such as `%(patient_id)s`, with a separate parameter
dictionary. Do not interpolate values using f-strings, `format`, or the percent
operator. Parameterisation applies to values; choose table/column names from
known schema definitions. Check that joins have the intended grain and do not
silently duplicate fields. Empty results may indicate the wrong identifier,
filters, database, or permissions; they do not prove no treatment occurred.

## Load a field's delivery data

`pymedphys.Delivery.from_mosaiq(connection, field_id)` reads the control-point
information for an internal `TxField.FLD_ID`. Inspect the report above and select
an actual field ID rather than substituting the patient ID, field label, or
row index. Use it inside the open connection context, then check control-point
count and final MU against the intended field. See [Delivery data](delivery.md).

For associating a recorded TRF with a treatment, use
`pymedphys.trf.identify(connection, path, timezone=...)`; that query relies on
machine/time/field details. The database time zone must be explicit for that
workflow. Generic `execute` returns stored datetime values without applying
that conversion. Preserve their time-zone meaning when comparing systems or
exporting reports. See [Work with logfiles](logfiles.md).

## Diagnose connection and query failures

- Connection failure: check the approved host, port, route/firewall, SQL Server
  availability, database name, and account permissions.
- Login failure: check the credentials for this hostname/port/database and the
  operating-system account running the process.
- Keyring or prompt failure: use both explicit credentials through an approved
  secret mechanism in unattended environments.
- Query error: inspect the schema and placeholder/parameter names. Confirm that
  the account has access to the requested tables.
- Unexpected rows: check joins, identifiers, duplicates, exclusions, and time
  interpretation before drawing a conclusion.

Keep local query outputs and exceptions within the authorised data environment;
they may include identifiers. The [Mosaiq API reference](../ref/lib/mosaiq.rst)
defines signatures. App connection fields are described in
[configuration](../ref/configuration.md#add-delivery-sources). The experimental
Mosaiq AI chat app has additional data-sharing behaviour described in
[Use the apps](apps.md#experimental-apps).
