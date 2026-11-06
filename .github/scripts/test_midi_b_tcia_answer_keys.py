"""Tests of midi_b_tcia_answer_keys.py's fetch and network record."""

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


PAGE = '<a href="https://faspex.cancerimagingarchive.net/p?context=a&amp;x=1">'
UNAVAILABLE = "ERRR Rest: faspex.cancerimagingarchive.net 503 Service Unavailable\n"
UNAVAILABLE_REASON = (
    "ascli stopped on a Rest error, HTTP 503 (Service Unavailable), "
    "naming faspex.cancerimagingarchive.net."
)


def _resolved(address):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]


class AscliFailureTests(unittest.TestCase):
    def test_names_a_failed_requests_status_and_host(self):
        logged = "INFO Saving config file\n" + UNAVAILABLE
        self.assertEqual(keys.ascli_failure(logged), [UNAVAILABLE_REASON])

    def test_finds_the_status_after_the_apis_own_messages(self):
        # ascli runs its Aspera handlers before its generic one, so the API's
        # own messages come first and the host and status last, each on a
        # line of its own (aspera-cli 4.27's RestErrorAnalyzer). The lines
        # after the message are ascli's hints.
        logged = (
            "ERRR Rest: The package is not available\n"
            "code: 7\n"
            "faspex.cancerimagingarchive.net 404 Not Found\n"
            "Use --log-level=debug to get more details.\n"
        )
        self.assertEqual(
            keys.ascli_failure(logged),
            [
                "ascli stopped on a Rest error, HTTP 404 (Not Found), naming "
                "faspex.cancerimagingarchive.net."
            ],
        )

    def test_takes_no_status_from_a_line_without_a_host(self):
        self.assertEqual(
            keys.ascli_failure("ERRR Rest: Package 404 is gone\n"),
            ["ascli stopped on a Rest error."],
        )

    def test_ends_a_message_at_the_next_line_ascli_logs(self):
        logged = (
            "ERRR Rest: The package is not available\n"
            "INFO faspex.cancerimagingarchive.net 500 Internal Server Error\n"
        )
        self.assertEqual(keys.ascli_failure(logged), ["ascli stopped on a Rest error."])

    def test_reads_every_line_of_a_failed_trys_message(self):
        logged = (
            "WARN An error occurred during task: Session stopped\n"
            "check UDP port and firewall\n"
            "WARN Resuming in 2 seconds (retry left:6)\n"
            "ERRR Transfer: Maximum number of retry reached: 7\n"
        )
        self.assertEqual(
            keys.ascli_failure(logged),
            [
                "ascli stopped on a Transfer error; its messages mention UDP, "
                "a firewall, and the retry limit.",
                "ascli logged 1 failed try of the transfer.",
            ],
        )

    def test_gives_a_status_without_a_name_by_its_number(self):
        logged = "ERRR Rest: faspex.cancerimagingarchive.net:443 599 Odd\n"
        self.assertEqual(
            keys.ascli_failure(logged),
            [
                "ascli stopped on a Rest error, HTTP 599, naming "
                "faspex.cancerimagingarchive.net:443."
            ],
        )

    def test_reads_the_line_ascli_logged_when_a_host_did_not_resolve(self):
        # As aspera-cli 4.27.2 logged it, on 5 Nov 2026, when ibm.biz did
        # not resolve.
        logged = (
            "WARN No config file found.\n"
            "ERRR Network: Failed to open TCP connection to ibm.biz:443 "
            "(getaddrinfo: Name or service not known)\n"
        )
        self.assertEqual(
            keys.ascli_failure(logged),
            [
                "ascli stopped on a Network error; its message mentions TCP "
                "and name resolution."
            ],
        )

    def test_counts_the_failed_tries_and_reads_their_messages(self):
        lost = (
            "WARN An error occurred during task: Timeout establishing data "
            "connection (check UDP port and firewall)\n"
        )
        logged = (
            f"{lost}WARN Resuming in 2 seconds (retry left:6)\n"
            f"{lost}WARN Resuming in 4 seconds (retry left:5)\n"
            "ERRR Transfer: Maximum number of retry reached: 7\n"
        )
        self.assertEqual(
            keys.ascli_failure(logged),
            [
                "ascli stopped on a Transfer error; its messages mention a "
                "timeout, UDP, a firewall, and the retry limit.",
                "ascli logged 2 failed tries of the transfer.",
            ],
        )

    def test_names_the_class_of_an_other_error(self):
        logged = (
            "ERRR Other(Net::ReadTimeout): Net::ReadTimeout with "
            "#<TCPSocket:(closed)>\n"
        )
        self.assertEqual(
            keys.ascli_failure(logged),
            [
                "ascli stopped on an Other(Net::ReadTimeout) error; its "
                "message mentions a timeout."
            ],
        )

    def test_never_prints_a_message(self):
        logged = (
            "WARN An error occurred during task: cannot write "
            "/tmp/x/MIDI-B-Answer-Key-Test.zip\n"
            "ERRR Transfer: cannot write /tmp/x/MIDI-B-Answer-Key-Test.zip from "
            "https://faspex.cancerimagingarchive.net/aspera/faspex/public/"
            "package?context=c2VjcmV0\n"
        )
        lines = keys.ascli_failure(logged)
        self.assertEqual(
            lines,
            [
                "ascli stopped on a Transfer error, naming "
                "faspex.cancerimagingarchive.net.",
                "ascli logged 1 failed try of the transfer.",
            ],
        )
        for value in ("/tmp", "MIDI-B", "https", "context", "c2VjcmV0"):
            self.assertNotIn(value, "\n".join(lines))

    def test_names_each_category_with_its_article(self):
        for category, named in (
            ("SSL", "an SSL"),
            ("Schema", "a Schema"),
            ("Identifier", "an Identifier"),
            ("UnusedArg", "an UnusedArg"),
        ):
            with self.subTest(category=category):
                self.assertEqual(
                    keys.ascli_failure(f"ERRR {category}: x\n"),
                    [f"ascli stopped on {named} error."],
                )

    def test_takes_the_last_error_it_logged(self):
        logged = UNAVAILABLE + "ERRR Transfer: Connection lost\n"
        self.assertEqual(
            keys.ascli_failure(logged),
            [
                "ascli stopped on a Transfer error; its message mentions a lost "
                "connection."
            ],
        )

    def test_says_when_the_error_is_of_a_kind_it_does_not_know(self):
        self.assertEqual(
            keys.ascli_failure("ERRR ascp failed (pid 7 exit 1)\n"),
            ["ascli logged an error of a kind this script does not know."],
        )

    def test_says_when_ascli_logged_no_error(self):
        self.assertEqual(
            keys.ascli_failure("INFO Saving config file\n"),
            ["ascli logged no error."],
        )


class FetchTests(unittest.TestCase):
    def fetch(self, outcomes):
        """Fetch with ascli exiting with each (status, what it logs) in turn.

        Returns fetch's status, the printed lines, the pauses, and the names
        in the package's folder as each try began.
        """
        found = []

        def run(command, stdout, stderr, check):
            status, logged = outcomes[len(found)]
            folder = Path(command[5].removeprefix("--to-folder="))
            found.append(sorted(path.name for path in folder.iterdir()))
            (folder / "partial").write_bytes(b"")
            stdout.write(logged)
            return subprocess.CompletedProcess(command, status)

        output = StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(keys, "_page", return_value=PAGE),
            mock.patch.object(keys, "utc_now", return_value="2026-11-05T22:06:27Z"),
            mock.patch.object(keys.subprocess, "run", side_effect=run),
            mock.patch.object(keys.time, "sleep") as sleep,
            redirect_stdout(output),
        ):
            status = keys.fetch(Path(directory) / "tcia")
        pauses = [call.args[0] for call in sleep.call_args_list]
        return status, output.getvalue().splitlines(), pauses, found

    def test_tries_a_failed_package_again_and_says_why_it_failed(self):
        status, lines, pauses, found = self.fetch([(1, UNAVAILABLE), (0, "")])
        self.assertEqual(status, 0)
        self.assertEqual(
            lines,
            [
                "Package 1 of 1: ascli exited with 1 at 2026-11-05T22:06:27Z",
                UNAVAILABLE_REASON,
                "Receiving package 1: attempt 1 of 3 failed; trying again in 60 s.",
                "Package 1 of 1: ascli exited with 0 at 2026-11-05T22:06:27Z",
            ],
        )
        self.assertEqual(pauses, [keys.PACKAGE_PAUSE])
        # The failed try's files were removed before the next.
        self.assertEqual(found, [[], []])

    def test_gives_up_on_a_package_after_three_tries(self):
        status, lines, pauses, found = self.fetch([(1, UNAVAILABLE)] * 3)
        self.assertEqual(status, 1)
        self.assertEqual(len(found), keys.PACKAGE_ATTEMPTS)
        self.assertEqual(pauses, [60.0, 120.0])
        self.assertEqual(
            lines[-2:],
            [
                "Package 1 of 1: ascli exited with 1 at 2026-11-05T22:06:27Z",
                UNAVAILABLE_REASON,
            ],
        )

    def test_reads_only_what_each_try_logged(self):
        status, lines, _, _ = self.fetch(
            [(1, UNAVAILABLE), (2, "INFO Saving config file\n"), (0, "")]
        )
        self.assertEqual(status, 0)
        self.assertEqual(
            [line for line in lines if line.startswith("ascli ")],
            [UNAVAILABLE_REASON, "ascli logged no error."],
        )

    def test_fails_when_the_page_links_no_package(self):
        output = StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(keys, "_page", return_value="<p>No links.</p>"),
            mock.patch.object(keys.subprocess, "run") as run,
            redirect_stdout(output),
        ):
            self.assertEqual(keys.fetch(Path(directory) / "tcia"), 1)
        run.assert_not_called()
        self.assertEqual(
            output.getvalue(), "TCIA's MIDI-B page links no Faspex package.\n"
        )


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
