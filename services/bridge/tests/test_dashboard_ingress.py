"""Dummy-only ingress tests: mocked DNS/connect, local socketpairs for relay."""

import contextlib
import io
from pathlib import Path
import socket
import socketserver
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dashboard_ingress as ingress
import inference_egress as egress


def answer(text="172.24.0.8", family=socket.AF_INET):
    address = (text, 9119) if family == socket.AF_INET else (text, 9119, 0, 0)
    return family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address


class FakeSocket:
    def __init__(self):
        self.closed = False
        self.sent = bytearray()
        self.timeouts = []
        self.connections = []
        self.recv = mock.Mock(side_effect=AssertionError("unexpected inspection"))

    def settimeout(self, value):
        self.timeouts.append(value)

    def connect(self, address):
        self.connections.append(address)

    def sendall(self, value):
        self.sent.extend(value)

    def shutdown(self, how):
        pass

    def close(self):
        self.closed = True


class AddressTests(unittest.TestCase):
    def test_explicit_rfc1918_and_ula_allowlist(self):
        for text in ("10.0.0.1", "10.255.255.254", "172.16.0.1", "172.31.255.254",
                     "192.168.0.1", "192.168.255.254", "fc00::1", "fdff:ffff::1"):
            with self.subTest(text=text):
                self.assertTrue(ingress.is_dashboard_address(text))

    def test_special_global_and_transition_addresses_denied(self):
        for text in ("8.8.8.8", "1.1.1.1", "172.15.255.255", "172.32.0.0", "192.0.0.9",
                     "127.0.0.1", "0.0.0.0", "169.254.1.1", "100.64.0.1", "192.0.2.1",
                     "198.18.0.1", "224.0.0.1", "240.0.0.1", "255.255.255.255", "::", "::1",
                     "fe80::1", "fe80::1%en0", "fd00::1%eth0", "ff02::1", "2001:4860::1",
                     "2001:db8::1", "2001::1", "2002:a00:1::1", "64:ff9b::a00:1",
                     "64:ff9b:1::a00:1", "::ffff:10.0.0.1", "::ffff:192.168.0.1", "3fff::1",
                     "10.0.0.1 ", "010.0.0.1", "hermes", "", None, True, 1):
            with self.subTest(text=text):
                self.assertFalse(ingress.is_dashboard_address(text))

    def test_only_fixed_literal_and_port_are_resolved(self):
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer()]) as lookup:
            self.assertEqual(ingress.resolve_dashboard(), [(socket.AF_INET, ("172.24.0.8", 9119))])
        lookup.assert_called_once_with("hermes", 9119, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        with self.assertRaises(TypeError):
            ingress.resolve_dashboard("attacker.invalid")
        with self.assertRaises(TypeError):
            ingress.connect_dashboard("127.0.0.1", 8123)

    def test_all_answers_validated_before_any_connection(self):
        for invalid in (answer("8.8.8.8"), answer("127.0.0.1"),
                        answer("::ffff:10.0.0.1", socket.AF_INET6)):
            with self.subTest(invalid=invalid), \
                    mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer(), invalid]), \
                    mock.patch.object(ingress.socket, "socket") as factory:
                with self.assertRaises(ingress.IngressError):
                    ingress.connect_dashboard()
                factory.assert_not_called()

    def test_malformed_dns_answers_fail_closed(self):
        ipv6 = answer("fd12:3456::9", socket.AF_INET6)
        invalid = (
            None, (), (socket.AF_INET,), list(answer()),
            (socket.AF_UNSPEC, *answer()[1:]),
            (socket.AF_INET, True, socket.IPPROTO_TCP, "", ("172.24.0.8", 9119)),
            (socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_TCP, "", ("172.24.0.8", 9119)),
            (socket.AF_INET, socket.SOCK_STREAM, True, "", ("172.24.0.8", 9119)),
            (*answer()[:4], ["172.24.0.8", 9119]),
            (*answer()[:4], ("172.24.0.8",)),
            (*answer()[:4], ("172.24.0.8", 8123)),
            (*answer()[:4], ("172.24.0.8", 9119.0)),
            (*answer()[:4], ("172.24.0.8", True)),
            (*answer()[:4], ("fd12::9", 9119)),
            (*ipv6[:4], ("172.24.0.8", 9119, 0, 0)),
            (*ipv6[:4], ("fd12::9", 9119, 1, 0)),
            (*ipv6[:4], ("fd12::9", 9119, 0, 1)),
            (*ipv6[:4], ("fd12::9", 9119, False, 0)),
            (*ipv6[:4], ("fd12::9", 9119, 0, 0.0)),
            (*answer()[:4], (None, 9119)),
        )
        for row in invalid:
            with self.subTest(row=row), \
                    mock.patch.object(ingress.socket, "getaddrinfo", return_value=[row]), \
                    mock.patch.object(ingress.socket, "socket") as factory:
                with self.assertRaises(ingress.IngressError):
                    ingress.connect_dashboard()
                factory.assert_not_called()

    def test_empty_excessive_and_nonlist_dns_results_denied(self):
        for rows in ([], None, (), [answer()] * 17):
            with self.subTest(rows=rows), mock.patch.object(ingress.socket, "getaddrinfo", return_value=rows):
                with self.assertRaises(ingress.IngressError):
                    ingress.resolve_dashboard()
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer()] * 16):
            self.assertEqual(len(ingress.resolve_dashboard()), 1)

    def test_fresh_resolution_and_ipv4_first_deduplication(self):
        rows = [answer("fd12:3456:0:0:0:0:0:9", socket.AF_INET6), answer(), answer(),
                answer("fd12:3456::9", socket.AF_INET6)]
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=rows) as lookup:
            expected = [(socket.AF_INET, ("172.24.0.8", 9119)),
                        (socket.AF_INET6, ("fd12:3456::9", 9119, 0, 0))]
            self.assertEqual(ingress.resolve_dashboard(), expected)
            self.assertEqual(ingress.resolve_dashboard(), expected)
            self.assertEqual(lookup.call_count, 2)

    def test_lookup_failure_uses_fixed_error(self):
        with mock.patch.object(ingress.socket, "getaddrinfo", side_effect=socket.gaierror("private details")):
            with self.assertRaisesRegex(ingress.IngressError, "^dashboard_unavailable$"):
                ingress.resolve_dashboard()


class ConnectionTests(unittest.TestCase):
    def test_numeric_pinning_ipv4_preference_and_io_timeout(self):
        candidate = FakeSocket()
        rows = [answer("fd12::9", socket.AF_INET6), answer()]
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=rows) as lookup, \
                mock.patch.object(ingress.socket, "socket", return_value=candidate) as factory:
            self.assertIs(ingress.connect_dashboard(), candidate)
        factory.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.assertEqual(candidate.connections, [("172.24.0.8", 9119)])
        self.assertGreater(candidate.timeouts[0], 0)
        self.assertLessEqual(candidate.timeouts[0], 2)
        self.assertEqual(candidate.timeouts[-1], 5)
        self.assertFalse(candidate.closed)
        self.assertEqual(lookup.call_args.args, ("hermes", 9119))

    def test_failed_attempt_closed_then_native_ipv6_used(self):
        first, second = FakeSocket(), FakeSocket()
        first.connect = mock.Mock(side_effect=TimeoutError("private details"))
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer(), answer("fd12::9", socket.AF_INET6)]), \
                mock.patch.object(ingress.socket, "socket", side_effect=[first, second]) as factory:
            self.assertIs(ingress.connect_dashboard(), second)
        self.assertTrue(first.closed)
        self.assertEqual(second.connections, [("fd12::9", 9119, 0, 0)])
        self.assertEqual(factory.call_args.args, (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP))

    def test_shared_deadline_caps_later_attempt(self):
        first, second = FakeSocket(), FakeSocket()
        first.connect = second.connect = mock.Mock(side_effect=OSError("private details"))
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer(), answer("fd12::9", socket.AF_INET6)]), \
                mock.patch.object(ingress.socket, "socket", side_effect=[first, second]), \
                mock.patch.object(ingress.time, "monotonic", side_effect=[0.0, 0.0, 4.75]):
            with self.assertRaisesRegex(ingress.IngressError, "^dashboard_unavailable$"):
                ingress.connect_dashboard()
        self.assertEqual(first.timeouts, [2.0])
        self.assertEqual(second.timeouts, [0.25])
        self.assertTrue(first.closed and second.closed)

    def test_deadline_exhaustion_skips_second_socket(self):
        first = FakeSocket()
        first.connect = mock.Mock(side_effect=OSError("private details"))
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer(), answer("fd12::9", socket.AF_INET6)]), \
                mock.patch.object(ingress.socket, "socket", return_value=first) as factory, \
                mock.patch.object(ingress.time, "monotonic", side_effect=[0.0, 0.0, 5.01]):
            with self.assertRaises(ingress.IngressError):
                ingress.connect_dashboard()
        self.assertEqual(factory.call_count, 1)
        self.assertTrue(first.closed)

    def test_socket_factory_failure_tries_next_address(self):
        candidate = FakeSocket()
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer(), answer("fd12::9", socket.AF_INET6)]), \
                mock.patch.object(ingress.socket, "socket", side_effect=[OSError("no socket"), candidate]):
            self.assertIs(ingress.connect_dashboard(), candidate)
        self.assertEqual(candidate.connections, [("fd12::9", 9119, 0, 0)])

    def test_setup_failure_closes_candidate(self):
        candidate = FakeSocket()
        candidate.settimeout = mock.Mock(side_effect=OSError("private setup details"))
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer()]), \
                mock.patch.object(ingress.socket, "socket", return_value=candidate):
            with self.assertRaises(ingress.IngressError):
                ingress.connect_dashboard()
        self.assertTrue(candidate.closed)

    def test_unexpected_exception_still_closes_candidate(self):
        candidate = FakeSocket()
        candidate.connect = mock.Mock(side_effect=ValueError("private details"))
        with mock.patch.object(ingress.socket, "getaddrinfo", return_value=[answer()]), \
                mock.patch.object(ingress.socket, "socket", return_value=candidate):
            with self.assertRaises(ValueError):
                ingress.connect_dashboard()
        self.assertTrue(candidate.closed)


class HandlerTests(unittest.TestCase):
    def test_accepted_bytes_are_not_inspected_or_prefixed(self):
        incoming, upstream = FakeSocket(), FakeSocket()
        with mock.patch.object(ingress, "connect_dashboard", return_value=upstream) as connect, \
                mock.patch.object(ingress, "relay_tunnel") as relay:
            ingress.DashboardHandler(incoming, ("203.0.113.1", 1), None)
        connect.assert_called_once_with()
        relay.assert_called_once_with(incoming, upstream)
        incoming.recv.assert_not_called()
        self.assertEqual(incoming.sent, b"")
        self.assertTrue(incoming.closed and upstream.closed)

    def test_connect_failure_closes_client_without_logging(self):
        incoming = FakeSocket()
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(ingress, "connect_dashboard", side_effect=OSError("fixture credential")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            ingress.DashboardHandler(incoming, ("127.0.0.1", 1), None)
        self.assertTrue(incoming.closed)
        self.assertEqual(incoming.sent, b"")
        self.assertEqual(output.getvalue() + errors.getvalue(), "")

    def test_relay_failure_closes_both_without_output(self):
        incoming, upstream = FakeSocket(), FakeSocket()
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(ingress, "connect_dashboard", return_value=upstream), \
                mock.patch.object(ingress, "relay_tunnel", side_effect=OSError("fixture credential")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            ingress.DashboardHandler(incoming, ("127.0.0.1", 1), None)
        self.assertTrue(incoming.closed and upstream.closed)
        self.assertEqual(incoming.sent, b"")
        self.assertEqual(output.getvalue() + errors.getvalue(), "")


class SocketPairTests(unittest.TestCase):
    def test_opaque_http_websocket_bytes_and_bidirectional_half_close(self):
        incoming, client = socket.socketpair()
        upstream, dashboard = socket.socketpair()
        peers = incoming, client, upstream, dashboard
        for peer in peers:
            peer.settimeout(1)
        request = (b"GET /ws HTTP/1.1\r\nHost: untrusted.invalid:22\r\n"
                   b"Upgrade: websocket\r\nAuthorization: Bearer fixture-only\r\n\r\n"
                   + bytes(range(256)) * 300)
        response = b"HTTP/1.1 101 Switching Protocols\r\n\r\n\x82\x04\x00\xff\x01\x80"
        failures = []

        def worker():
            try:
                with mock.patch.object(ingress, "connect_dashboard", return_value=upstream), \
                        mock.patch.object(ingress, "relay_tunnel", side_effect=lambda a, b:
                                          egress.relay_tunnel(a, b, idle_timeout=0.5, lifetime=2)):
                    ingress.DashboardHandler(incoming, ("127.0.0.1", 1), None)
            except Exception as error:
                failures.append(type(error).__name__)

        def writer():
            try:
                client.sendall(request)
                client.shutdown(socket.SHUT_WR)
            except Exception as error:
                failures.append(type(error).__name__)

        def read_all(peer):
            result = bytearray()
            while chunk := peer.recv(8192):
                result.extend(chunk)
            return bytes(result)

        thread = threading.Thread(target=worker, daemon=True)
        sender = threading.Thread(target=writer, daemon=True)
        thread.start()
        sender.start()
        try:
            self.assertEqual(read_all(dashboard), request)
            dashboard.sendall(response)
            dashboard.shutdown(socket.SHUT_WR)
            self.assertEqual(read_all(client), response)
            sender.join(1)
            thread.join(1)
            self.assertFalse(sender.is_alive() or thread.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual((incoming.fileno(), upstream.fileno()), (-1, -1))
        finally:
            ingress.close_sockets(*peers)
            sender.join(1)
            thread.join(1)

    def test_shared_relay_idle_bound_closes_both(self):
        incoming, client = socket.socketpair()
        upstream, dashboard = socket.socketpair()
        try:
            with mock.patch.object(ingress, "connect_dashboard", return_value=upstream), \
                    mock.patch.object(ingress, "relay_tunnel", side_effect=lambda a, b:
                                      egress.relay_tunnel(a, b, idle_timeout=0.02, lifetime=0.1)):
                ingress.DashboardHandler(incoming, ("127.0.0.1", 1), None)
            self.assertEqual((incoming.fileno(), upstream.fileno()), (-1, -1))
        finally:
            ingress.close_sockets(incoming, client, upstream, dashboard)


class ServerTests(unittest.TestCase):
    def make_server(self):
        with mock.patch.object(socketserver.TCPServer, "__init__", return_value=None):
            return ingress.DashboardIngressServer(("127.0.0.1", 9119))

    def test_custom_handler_installed_before_serving_and_shared_engine(self):
        server = self.make_server()
        self.assertIs(server.RequestHandlerClass, ingress.DashboardHandler)
        self.assertIs(ingress.DashboardIngressServer.process_request, egress.EgressServer.process_request)
        self.assertIs(ingress.DashboardIngressServer.process_request_thread, egress.EgressServer.process_request_thread)
        self.assertIs(ingress.DashboardIngressServer.handle_error, egress.EgressServer.handle_error)
        self.assertIs(ingress.relay_tunnel, egress.relay_tunnel)
        self.assertIs(ingress.close_sockets, egress.close_sockets)

    def test_inherited_admission_is_bounded_to_sixteen(self):
        server = self.make_server()
        for _ in range(16):
            self.assertTrue(server._slots.acquire(blocking=False))
        incoming = FakeSocket()
        with mock.patch.object(egress.socketserver.ThreadingMixIn, "process_request") as start:
            server.process_request(incoming, ("127.0.0.1", 1))
        start.assert_not_called()
        self.assertTrue(incoming.closed)
        self.assertTrue(incoming.sent.startswith(b"HTTP/1.1 503 "))
        self.assertFalse(server._slots.acquire(blocking=False))

    def test_exact_cli_only_sets_listener(self):
        with mock.patch.object(ingress, "DashboardIngressServer") as factory:
            ingress.main(["--host", "0.0.0.0", "--port", "9119"])
        factory.assert_called_once_with(("0.0.0.0", 9119))
        factory.return_value.__enter__.return_value.serve_forever.assert_called_once_with(poll_interval=0.5)

    def test_default_cli_and_keyboard_interrupt(self):
        with mock.patch.object(ingress, "DashboardIngressServer") as factory:
            factory.return_value.__enter__.return_value.serve_forever.side_effect = KeyboardInterrupt
            ingress.main([])
        factory.assert_called_once_with(("0.0.0.0", 9119))

    def test_cli_rejects_upstream_and_policy_bypass_flags(self):
        for args in (["--upstream", "127.0.0.1"], ["--target", "home-assistant:8123"],
                     ["--allow-private"], ["--no-verify"], ["--port", "0"], ["--port", "65536"]):
            with self.subTest(args=args), mock.patch.object(ingress, "DashboardIngressServer") as factory, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    ingress.main(args)
                self.assertEqual(error.exception.code, 2)
                factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
