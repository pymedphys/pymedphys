# Work with logfiles

A TRF is a recorded machine delivery extracted from Elekta diagnostic backups.
An iCOM stream is captured from a live endpoint and later split into patient
sessions. TRF decoding can run entirely from a local file; identifying its
treatment record requires Mosaiq. An archived iCOM session can be read offline
after decompression, while its listener needs a live connection. Neither
source independently verifies the physical MLC or jaw position.

Use native Elekta Agility TRFs to inspect recorded machine values, or record an
iCOM stream from an authorised Elekta endpoint. Neither route makes the machine
record an independent measurement of physical delivery. The
[historical project explanation](../background/elekta-logfiles.rst) gives that
context; the procedures below describe the current interfaces.

## Decode a TRF without a database

Install `pymedphys[trf]` or the recommended `user` extra. Work on an approved
TRF copied into a practice directory. The file must be a native TRF, rather
than a renamed CSV or diagnostics ZIP.

```python
from pathlib import Path
import pymedphys

path = Path("example.trf")
header, table = pymedphys.trf.read(path)
assert len(header) == 1
print(f"Decoded rows: {len(table)}")
print(table.columns.tolist())
header.to_csv("decoded-header.csv", index=False)
table.to_csv("decoded-table.csv")
delivery = pymedphys.Delivery.from_trf(path)
print(f"Delivery control points: {len(delivery.mu)}")
```

`header` and `table` are pandas DataFrames. The table has decoded column names
with their units and an elapsed-time index. Check header machine, timestamp,
field label/name, table row count, and MU against the record you intended to
load. Keep the original alongside a version and hash record for reproducibility.
See the [TRF reference](../ref/lib/trf.rst) and [Delivery guide](delivery.md).

For a shell workflow:

```bash
pymedphys trf to-csv "example.trf"
```

It creates `example_header.csv` and `example_table.csv` beside the source.
`pymedphys trf to-csv "*.trf"` converts matching files; check that files actually
matched, as an empty glob can finish without outputs. The command writes CSVs
beside each input, so copy sources to a writable output directory first.
An encoding/column error should be investigated against the native file and
its exporter version; `pymedphys trf detect example.trf` is an encoding diagnostic,
not a repair or a patient-identification command.

## Associate a TRF with Mosaiq

Install `pymedphys[trf,mosaiq]` or `user`. Establish an authorised read-only
connection as described in [Query Mosaiq](mosaiq.md). Then:

```python
from pathlib import Path
import pymedphys

with pymedphys.mosaiq.connect("mosaiq.example.org") as connection:
    details = pymedphys.trf.identify(
        connection, Path("example.trf"), timezone="Australia/Sydney"
    )
    print(f"Field ID: {details.field_id}; QA mode: {details.qa_mode}")
```

Substitute the **Mosaiq database's time zone**, including daylight saving rules,
for the example. Identification converts the TRF UTC timestamp to that zone,
then matches machine name, delivery time, field label, and field name.
The result contains patient identifiers as well as field details; handle it
within the authorised environment. A missing field label, no matching entry,
or disagreeing matches stops identification. Check the time zone, clocks,
machine naming, and field values before widening your workflow's assumptions.

`pymedphys trf orchestrate` fetches diagnostic backups, extracts TRFs, and indexes
them using Mosaiq. It changes its configured archive/index directories. Configure
and validate a dedicated location and the authorised network shares first;
see [configuration](../ref/configuration.md#configure-trf-orchestration). It is a single
run, so daily scheduling belongs in your service or scheduler. Verify indexed
records and error directories after each run rather than interpreting a
completed fetch as successful identification of every file.

## Record an iCOM stream

Install `pymedphys[icom]` or `user`. Obtain the endpoint IP, TCP access to port
1706, and a writable storage directory from the people responsible for the
machine and network. The CLI's IP is the **remote endpoint**, not an address
on which PyMedPhys listens:

```bash
pymedphys --verbose icom listen 192.0.2.10 icom-records
```

`192.0.2.10` is a documentation placeholder; replace it. The listener connects
outbound, runs continuously, and writes:

| Location | Contents |
| --- | --- |
| `icom-records/live/<IP>/<counter>.txt` | Recent complete stream items, using a cyclic counter from 000 to 255; these files are overwritten as counters recur. |
| `icom-records/patients/<encoded-ID_name>/<start-time>.xz` | Compressed patient-associated streams after a patient session completes. |
| `icom-records/patients/unknown_error_in_record/...` | Streams that could not be converted into Delivery data. |

The patient archive is saved when the stream's patient ID becomes absent after
an active session. A record with no delivered MU is not saved. Live files are
a rolling buffer, not a permanent archive. An active session is held in memory;
stopping or restarting the process is not a guarantee of saving that session.
Identifiers appear in archive paths and operational logs.

After a 10-second receive timeout, the listener reconnects. If recording raises
an error, the CLI prints the traceback and retries after 15 minutes. These
behaviours do not guarantee uninterrupted recording. Supervise the process,
monitor recent live files and completed archive counts, and investigate gaps
and `unknown_error_in_record`. Stop with Ctrl+C. For unattended use, set the
working directory, interpreter, account/storage access, log rotation, restart
policy, and health checks explicitly in your service manager; validate on a
non-patient session before relying on it.

Read an archived stream as bytes:

```python
import lzma
import pymedphys

with lzma.open("completed-session.xz", "rb") as archive:
    delivery = pymedphys.Delivery.from_icom(archive.read())
assert len(delivery.mu) > 0
print(f"Recorded MU: {delivery.mu[-1]:.1f}")
```

The library normalises cumulative MU increments and converts collimation to its
common representation. Compare against known input expectations, not only
whether parsing succeeded. The [iCOM command reference](../ref/cli/icom.rst)
gives exact arguments. [Adding a Linac](../howto/add-a-linac.md) and the
[tunnel notes](../howto/tunnels/index.md) remain historical deployment records.

```{toctree}
:hidden:

../background/elekta-logfiles
```
