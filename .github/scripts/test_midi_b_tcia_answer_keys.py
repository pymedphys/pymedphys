"""Tests of midi_b_tcia_answer_keys.py's network record."""

import socket
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import midi_b_tcia_answer_keys as keys

TRACE = """traceroute to 192.0.2.7 (192.0.2.7), 30 hops max, 60 byte packets
 1  * * *
 2  192.0.2.1 (192.0.2.1)  1.000 ms  1.100 ms  1.200 ms
"""


def _resolved(address):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]


class TraceTests(unittest.TestCase):
    def test_prints_the_trace_after_when_it_started(self):
        completed = subprocess.CompletedProcess([], 0, stdout=TRACE)
        with (
            mock.patch.object(keys, "utc_now", return_value="2026-11-05T20:00:00Z"),
            mock.patch.object(keys.subprocess, "run", return_value=completed) as run,
        ):
            lines = keys.trace("www.example.org", "192.0.2.7")
        self.assertEqual(
            lines,
            [
                "ICMP trace to www.example.org (192.0.2.7) at 2026-11-05T20:00:00Z:",
                *TRACE.splitlines(),
            ],
        )
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["sudo", "-n", "traceroute", "-I"])
        self.assertEqual(command[-1], "192.0.2.7")
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.STDOUT)
        self.assertEqual(run.call_args.kwargs["timeout"], keys.TRACE_TIMEOUT)
        self.assertFalse(run.call_args.kwargs["check"])

    def test_says_how_a_failed_trace_exited(self):
        completed = subprocess.CompletedProcess(
            [], 1, stdout="sudo: traceroute: command not found\n"
        )
        with mock.patch.object(keys.subprocess, "run", return_value=completed):
            lines = keys.trace("www.example.org", "192.0.2.7")
        self.assertEqual(
            lines[1:],
            ["sudo: traceroute: command not found", "traceroute exited with 1."],
        )

    def test_keeps_what_a_trace_printed_before_it_was_stopped(self):
        expired = subprocess.TimeoutExpired(
            [], keys.TRACE_TIMEOUT, output=TRACE.encode()
        )
        with mock.patch.object(keys.subprocess, "run", side_effect=expired):
            lines = keys.trace("www.example.org", "192.0.2.7")
        self.assertEqual(
            lines[1:],
            [*TRACE.splitlines(), "The trace was stopped after 45 s."],
        )

    def test_says_that_a_trace_stopped_before_printing_anything(self):
        expired = subprocess.TimeoutExpired([], keys.TRACE_TIMEOUT)
        with mock.patch.object(keys.subprocess, "run", side_effect=expired):
            lines = keys.trace("www.example.org", "192.0.2.7")
        self.assertEqual(lines[1:], ["The trace was stopped after 45 s."])

    def test_says_why_there_is_no_trace_without_sudo(self):
        with mock.patch.object(
            keys.subprocess, "run", side_effect=FileNotFoundError("sudo")
        ):
            lines = keys.trace("www.example.org", "192.0.2.7")
        self.assertEqual(
            lines[1:],
            ["There is no trace: sudo could not run (FileNotFoundError)."],
        )

    def test_four_traces_fit_the_workflow_step(self):
        # The step allows 5 minutes; the address and connection checks need
        # the rest.
        self.assertLessEqual((len(keys.HOSTS) + 1) * keys.TRACE_TIMEOUT, 180)


class Ipv4AddressTests(unittest.TestCase):
    def test_gives_the_first_address(self):
        found = [*_resolved("192.0.2.7"), *_resolved("192.0.2.8")]
        with mock.patch.object(
            keys.socket, "getaddrinfo", return_value=found
        ) as lookup:
            self.assertEqual(keys.ipv4_address("www.example.org"), "192.0.2.7")
        self.assertEqual(lookup.call_args.args[2], socket.AF_INET)

    def test_gives_none_for_a_host_that_does_not_resolve(self):
        with mock.patch.object(
            keys.socket, "getaddrinfo", side_effect=socket.gaierror("no name")
        ):
            self.assertIsNone(keys.ipv4_address("www.example.org"))


class NetworkTests(unittest.TestCase):
    def test_traces_each_address_once_and_the_control_host(self):
        addresses = {
            "www.cancerimagingarchive.net": "192.0.2.7",
            "services.cancerimagingarchive.net": "192.0.2.7",
            "faspex.cancerimagingarchive.net": "192.0.2.9",
            keys.TRACE_CONTROL: "198.51.100.3",
        }
        output = StringIO()
        with (
            mock.patch.object(keys, "public_address", return_value="203.0.113.5"),
            mock.patch.object(keys, "connect", side_effect=lambda host: [f"{host} ok"]),
            mock.patch.object(keys, "ipv4_address", side_effect=addresses.get),
            mock.patch.object(
                keys,
                "trace",
                side_effect=lambda host, address: [f"trace {host} {address}"],
            ) as trace,
            redirect_stdout(output),
        ):
            self.assertEqual(keys.network(), 0)
        self.assertEqual(
            [call.args for call in trace.call_args_list],
            [
                ("www.cancerimagingarchive.net", "192.0.2.7"),
                ("faspex.cancerimagingarchive.net", "192.0.2.9"),
                (keys.TRACE_CONTROL, "198.51.100.3"),
            ],
        )
        lines = output.getvalue().splitlines()
        self.assertIn("this runner's public address is 203.0.113.5.", lines[0])
        self.assertEqual(
            lines[1:],
            [
                "www.cancerimagingarchive.net ok",
                "services.cancerimagingarchive.net ok",
                "faspex.cancerimagingarchive.net ok",
                "trace www.cancerimagingarchive.net 192.0.2.7",
                "trace faspex.cancerimagingarchive.net 192.0.2.9",
                f"trace {keys.TRACE_CONTROL} 198.51.100.3",
            ],
        )

    def test_says_which_hosts_have_no_address_to_trace(self):
        output = StringIO()
        with (
            mock.patch.object(keys, "public_address", return_value=None),
            mock.patch.object(keys, "connect", return_value=[]),
            mock.patch.object(keys, "ipv4_address", return_value=None),
            mock.patch.object(keys, "trace") as trace,
            redirect_stdout(output),
        ):
            self.assertEqual(keys.network(), 0)
        trace.assert_not_called()
        lines = output.getvalue().splitlines()
        self.assertIn("public address is unknown.", lines[0])
        self.assertEqual(
            lines[1:],
            [
                f"There is no trace to {host}: it has no IPv4 address."
                for host in (*keys.HOSTS, keys.TRACE_CONTROL)
            ],
        )

    def test_appends_the_runner_address_to_github_env(self):
        with tempfile.TemporaryDirectory() as directory:
            github_env = Path(directory) / "github_env"
            github_env.write_text("EARLIER=1\n", encoding="utf-8")
            with (
                mock.patch.object(keys, "public_address", return_value="203.0.113.5"),
                mock.patch.object(keys, "connect", return_value=[]),
                mock.patch.object(keys, "ipv4_address", return_value=None),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(keys.network(github_env), 0)
            self.assertEqual(
                github_env.read_text(encoding="utf-8"),
                "EARLIER=1\nMIDI_B_RUNNER_ADDRESS=203.0.113.5\n",
            )


if __name__ == "__main__":
    unittest.main()
