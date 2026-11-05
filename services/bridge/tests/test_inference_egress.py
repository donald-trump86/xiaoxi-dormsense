"""Bounded local-only tests: DNS and outbound connects are always mocked."""

import contextlib
import io
from pathlib import Path
import socket
import socketserver
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inference_egress as egress

HOST = "inference-api.nousresearch.com"
TARGET = (HOST + ":443").encode("ascii")
REQUEST = b"CONNECT " + TARGET + b" HTTP/1.1\r\nHost: " + TARGET + b"\r\n\r\n"


class MemorySocket:
    def __init__(self, data=b""):
        self.data = bytearray(data)
        self.sent = bytearray()
        self.closed = False
        self.timeouts = []

    def recv(self, size):
        data = bytes(self.data[:size])
        del self.data[:size]
        return data

    def sendall(self, data):
        self.sent += data

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def close(self):
        self.closed = True

    def shutdown(self, how):
        pass


def answer(address, family=socket.AF_INET):
    sockaddr = (address, 443) if family == socket.AF_INET else (address, 443, 0, 0)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


def read_request(raw):
    return egress.read_connect_request(MemorySocket(raw), time.monotonic() + 2)


class RequestTests(unittest.TestCase):
    def assert_rejected(self, raw, status):
        with self.assertRaises(egress.ProxyError) as caught:
            read_request(raw)
        self.assertEqual(caught.exception.status, status)

    def test_normal_http_11_and_both_allowed_targets(self):
        for host in sorted(egress.ALLOWED_HOSTS):
            with self.subTest(host=host):
                raw = REQUEST.replace(HOST.encode(), host.encode())
                self.assertEqual(read_request(raw), host)

    def test_http_10_host_optional_but_checked_if_present(self):
        self.assertEqual(read_request(b"CONNECT " + TARGET + b" HTTP/1.0\r\n\r\n"), HOST)
        self.assertEqual(read_request(REQUEST.replace(b"HTTP/1.1", b"HTTP/1.0")), HOST)
        self.assert_rejected(REQUEST.replace(TARGET, b"wrong.example:443", 1)
                             .replace(b"HTTP/1.1", b"HTTP/1.0"), 403)

    def test_header_names_case_insensitive_and_ows(self):
        raw = REQUEST.replace(b"Host: ", b"hOsT:\t").replace(
            b"\r\n\r\n", b"\t \r\nProxy-Connection: Keep-Alive\r\n\r\n")
        self.assertEqual(read_request(raw), HOST)

    def test_tunnel_bytes_are_not_consumed_as_headers(self):
        client = MemorySocket(REQUEST + b"\x16\x03\x01opaque")
        self.assertEqual(egress.read_connect_request(client, time.monotonic() + 2), HOST)
        self.assertEqual(client.data, b"\x16\x03\x01opaque")

    def test_unknown_authorities_rejected_before_dns(self):
        targets = (b"example.com:443", b"127.0.0.1:443", b"[::1]:443",
                   b"https://" + TARGET, TARGET + b"/", b"user@" + TARGET,
                   HOST.encode() + b":80", HOST.encode() + b":0443",
                   HOST.upper().encode() + b":443", TARGET + b".")
        with mock.patch.object(egress.socket, "getaddrinfo") as lookup:
            for target in targets:
                with self.subTest(target=target):
                    client = MemorySocket(REQUEST.replace(TARGET, target))
                    egress.EgressHandler(client, ("local", 0), object())
                    self.assertTrue(client.sent.startswith(b"HTTP/1.1 403 "))
                    self.assertTrue(client.closed)
            lookup.assert_not_called()

    def test_other_methods_rejected_before_dns(self):
        with mock.patch.object(egress.socket, "getaddrinfo") as lookup:
            for method in (b"GET", b"POST", b"connect", b"OPTIONS"):
                client = MemorySocket(REQUEST.replace(b"CONNECT", method, 1))
                egress.EgressHandler(client, ("local", 0), object())
                self.assertTrue(client.sent.startswith(b"HTTP/1.1 405 "))
            lookup.assert_not_called()

    def test_missing_mismatched_and_duplicate_host(self):
        cases = (
            b"CONNECT " + TARGET + b" HTTP/1.1\r\n\r\n",
            REQUEST.replace(b"Host: " + TARGET, b"Host: portal.nousresearch.com:443"),
            REQUEST.replace(b"\r\n\r\n", b"\r\nhost: " + TARGET + b"\r\n\r\n"),
            REQUEST.replace(b"Host: " + TARGET, b"Host: " + TARGET + b", " + TARGET),
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.assert_rejected(raw, 400)

    def test_all_body_framing_is_denied_even_zero_length(self):
        for header in (b"Content-Length: 0", b"Content-Length: 1",
                       b"Transfer-Encoding: chunked", b"Expect: 100-continue",
                       b"Trailer: Authorization"):
            with self.subTest(header=header):
                self.assert_rejected(REQUEST.replace(b"\r\n\r\n", b"\r\n" + header
                                                     + b"\r\n\r\n"), 400)

    def test_crlf_tokens_and_header_controls_are_strict(self):
        cases = (REQUEST.replace(b"\r\n", b"\n"),
                 REQUEST.replace(b"Host:", b"Host :"),
                 REQUEST.replace(b"Host:", b" Host:"),
                 REQUEST.replace(b"Host: ", b"Host: \x00"),
                 REQUEST.replace(b"Host: ", b"Host: \xff"),
                 REQUEST.replace(b"HTTP/1.1", b"HTTP/2.0"),
                 REQUEST.replace(b"CONNECT ", b"CONNECT  "),
                 REQUEST.replace(b"Host: ", b"X-Missing-Colon\r\nHost: "))
        for raw in cases:
            with self.subTest(raw=raw):
                self.assert_rejected(raw, 400)

    def test_request_line_count_and_total_limits(self):
        self.assert_rejected(b"C" * (egress.MAX_REQUEST_LINE + 1), 431)
        headers = b"X: a\r\n" * egress.MAX_HEADERS
        self.assert_rejected(REQUEST[:-2] + headers + b"\r\n", 431)
        raw = REQUEST[:-2] + b"X: " + b"a" * egress.MAX_HEADER_BYTES + b"\r\n\r\n"
        self.assert_rejected(raw, 431)

    def test_maximum_header_count_accepted(self):
        raw = REQUEST[:-2] + b"X: a\r\n" * (egress.MAX_HEADERS - 1) + b"\r\n"
        self.assertEqual(read_request(raw), HOST)

    def test_exact_total_header_limit(self):
        overhead = len(REQUEST[:-2] + b"X: \r\n\r\n")
        raw = REQUEST[:-2] + b"X: " + b"a" * (egress.MAX_HEADER_BYTES - overhead) + b"\r\n\r\n"
        self.assertEqual(len(raw), egress.MAX_HEADER_BYTES)
        self.assertEqual(read_request(raw), HOST)
        self.assert_rejected(raw[:-4] + b"a\r\n\r\n", 431)

    def test_truncated_headers_and_handshake_deadline(self):
        self.assert_rejected(REQUEST[:-1], 400)
        client = MemorySocket(REQUEST)
        with self.assertRaises(egress.ProxyError) as caught:
            egress.read_connect_request(client, time.monotonic() - 1)
        self.assertEqual(caught.exception.status, 408)
        client.recv = mock.Mock(side_effect=TimeoutError("private failure text"))
        with self.assertRaises(egress.ProxyError) as caught:
            egress.read_connect_request(client, time.monotonic() + 2)
        self.assertEqual(caught.exception.status, 408)


class AddressTests(unittest.TestCase):
    def test_ordinary_public_ipv4_ipv6(self):
        for address in ("1.1.1.1", "8.8.8.8", "104.18.0.1",
                        "2606:4700:4700::1111", "2001:4860:4860::8888"):
            with self.subTest(address=address):
                self.assertTrue(egress.is_public_address(address))

    def test_non_global_special_and_transition_addresses(self):
        addresses = (
            "0.0.0.0", "10.0.0.1", "100.64.0.1", "127.0.0.1", "169.254.1.1",
            "172.16.0.1", "192.0.0.9", "192.0.0.10", "192.0.2.1",
            "192.31.196.1", "192.52.193.1", "192.88.99.2", "192.168.1.1",
            "192.175.48.1", "198.18.1.1", "198.51.100.1", "203.0.113.1",
            "224.0.0.1", "240.0.0.1", "255.255.255.255", "::", "::1",
            "::ffff:8.8.8.8", "::8.8.8.8", "64:ff9b::808:808", "64:ff9b:1::1",
            "100::1", "2001::1", "2001:20::1", "2001:db8::1", "2002:808:808::1",
            "2620:4f:8000::1", "3ffe::1", "3fff::1", "5f00::1", "fc00::1",
            "fe80::1", "ff0e::1", "2606:4700::1%eth0", "1.2.3.004", "localhost",
            " 8.8.8.8", "8.8.8.8 ", None, 134744072,
        )
        for address in addresses:
            with self.subTest(address=address):
                self.assertFalse(egress.is_public_address(address))

    def test_unknown_host_is_denied_without_dns(self):
        with mock.patch.object(egress.socket, "getaddrinfo") as lookup:
            with self.assertRaises(egress.ProxyError) as caught:
                egress.resolve_addresses("unknown.example")
            self.assertEqual(caught.exception.status, 403)
            lookup.assert_not_called()

    def test_entire_mixed_dns_answer_rejected_before_any_connect(self):
        for special in (answer("10.0.0.1"), answer("192.0.0.9"),
                        answer("2002:808:808::1", socket.AF_INET6)):
            with self.subTest(special=special):
                with mock.patch.object(egress.socket, "getaddrinfo", return_value=[
                        answer("8.8.8.8"), special]), \
                        mock.patch.object(egress.socket, "socket") as create:
                    with self.assertRaises(egress.ProxyError):
                        egress.connect_upstream(HOST)
                    create.assert_not_called()

    def test_malformed_answers_fail_closed(self):
        good = answer("8.8.8.8")
        bad_answers = (
            (), None, (socket.AF_UNIX, *good[1:]),
            (good[0], socket.SOCK_DGRAM, *good[2:]),
            (*good[:2], 0, *good[3:]), (*good[:4], ("8.8.8.8", 80)),
            (*good[:4], ("8.8.8.8", 443.0)),
            (*good[:4], ("2001:4860::8888", 443)),
            (*answer("2606:4700::1", socket.AF_INET6)[:4], ("2606:4700::1", 443, 0, 1)),
            (*answer("2606:4700::1", socket.AF_INET6)[:4], ("2606:4700::1", 443, False, 0)),
        )
        for bad in bad_answers:
            with self.subTest(bad=bad):
                with mock.patch.object(egress.socket, "getaddrinfo", return_value=[good, bad]):
                    with self.assertRaises(egress.ProxyError):
                        egress.resolve_addresses(HOST)

    def test_dns_failure_empty_and_excessive_answers(self):
        for values in ([], [answer("8.8.8.8")] * (egress.MAX_DNS_RESULTS + 1)):
            with mock.patch.object(egress.socket, "getaddrinfo", return_value=values):
                with self.assertRaises(egress.ProxyError):
                    egress.resolve_addresses(HOST)
        with mock.patch.object(egress.socket, "getaddrinfo", side_effect=socket.gaierror("private")):
            with self.assertRaises(egress.ProxyError) as caught:
                egress.resolve_addresses(HOST)
            self.assertEqual(str(caught.exception), "proxy_rejected")

    def test_exact_numeric_pinning_and_ipv4_preference(self):
        upstream = mock.Mock()
        with mock.patch.object(egress.socket, "getaddrinfo", return_value=[
                answer("2606:4700:4700::1111", socket.AF_INET6), answer("8.8.8.8")]) as lookup, \
                mock.patch.object(egress.socket, "socket", return_value=upstream) as create, \
                mock.patch.object(egress.socket, "create_connection") as unpinned:
            self.assertIs(egress.connect_upstream(HOST), upstream)
            lookup.assert_called_once_with(HOST, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
            create.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            upstream.connect.assert_called_once_with(("8.8.8.8", 443))
            unpinned.assert_not_called()
            upstream.close.assert_not_called()

    def test_failed_attempt_closed_and_next_pinned_address_used(self):
        failed, succeeded = mock.Mock(), mock.Mock()
        failed.connect.side_effect = TimeoutError("private address details")
        with mock.patch.object(egress.socket, "getaddrinfo", return_value=[
                answer("8.8.8.8"), answer("2606:4700::1111", socket.AF_INET6)]), \
                mock.patch.object(egress.socket, "socket", side_effect=[failed, succeeded]):
            self.assertIs(egress.connect_upstream(HOST), succeeded)
        failed.close.assert_called_once()
        succeeded.connect.assert_called_once_with(("2606:4700::1111", 443, 0, 0))
        self.assertLessEqual(failed.settimeout.call_args_list[0].args[0], 2.0)

    def test_all_failures_close_sockets_and_share_deadline(self):
        failed = mock.Mock()
        failed.connect.side_effect = TimeoutError()
        with mock.patch.object(egress.socket, "getaddrinfo", return_value=[
                answer("8.8.8.8"), answer("1.1.1.1")]), \
                mock.patch.object(egress.socket, "socket", return_value=failed) as create, \
                mock.patch.object(egress.time, "monotonic", side_effect=[0.0, 0.0, 5.0]):
            with self.assertRaises(egress.ProxyError) as caught:
                egress.connect_upstream(HOST)
            self.assertEqual(caught.exception.status, 502)
            create.assert_called_once()
            failed.close.assert_called_once()

    def test_socket_setup_failure_closes_candidate(self):
        failed = mock.Mock()
        failed.settimeout.side_effect = OSError("private setup details")
        with mock.patch.object(egress.socket, "getaddrinfo", return_value=[answer("8.8.8.8")]), \
                mock.patch.object(egress.socket, "socket", return_value=failed):
            with self.assertRaises(egress.ProxyError):
                egress.connect_upstream(HOST)
        failed.close.assert_called_once()

    def test_each_connect_resolves_fresh(self):
        with mock.patch.object(egress.socket, "getaddrinfo", side_effect=[
                [answer("8.8.8.8")], [answer("1.1.1.1")]]) as lookup, \
                mock.patch.object(egress.socket, "socket") as create:
            first, second = mock.Mock(), mock.Mock()
            create.side_effect = [first, second]
            egress.connect_upstream(HOST).close()
            egress.connect_upstream(HOST).close()
        self.assertEqual(lookup.call_count, 2)
        first.connect.assert_called_once_with(("8.8.8.8", 443))
        second.connect.assert_called_once_with(("1.1.1.1", 443))


class HandlerTests(unittest.TestCase):
    def test_generic_errors_never_echo_exception_or_request(self):
        client = MemorySocket(REQUEST.replace(b"\r\n\r\n", b"\r\nAuthorization: secret-canary\r\n\r\n"))
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(egress, "connect_upstream", side_effect=OSError("secret-canary")), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            egress.EgressHandler(client, ("private-client", 0), object())
        self.assertEqual(client.sent, b"HTTP/1.1 502 Bad Gateway\r\nCache-Control: no-store\r\n"
                         b"Content-Length: 0\r\nConnection: close\r\n\r\n")
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")
        self.assertTrue(client.closed)

    def test_established_error_closes_both_without_http_in_tunnel(self):
        client, upstream = MemorySocket(REQUEST), MemorySocket()
        with mock.patch.object(egress, "connect_upstream", return_value=upstream), \
                mock.patch.object(egress, "relay_tunnel", side_effect=OSError("secret-canary")):
            egress.EgressHandler(client, ("local", 0), object())
        self.assertEqual(bytes(client.sent), b"HTTP/1.1 200 Connection Established\r\n"
                         b"Cache-Control: no-store\r\n\r\n")
        self.assertTrue(client.closed and upstream.closed)

    def test_response_write_failure_closes_already_connected_socket(self):
        client, upstream = MemorySocket(REQUEST), MemorySocket()
        client.sendall = mock.Mock(side_effect=OSError("private write details"))
        with mock.patch.object(egress, "connect_upstream", return_value=upstream):
            egress.EgressHandler(client, ("local", 0), object())
        self.assertTrue(client.closed and upstream.closed)


class RelayTests(unittest.TestCase):
    def sockets(self):
        client, client_peer = socket.socketpair()
        upstream, upstream_peer = socket.socketpair()
        for sock in (client, client_peer, upstream, upstream_peer):
            self.addCleanup(sock.close)
            sock.settimeout(1)
        return client, client_peer, upstream, upstream_peer

    @staticmethod
    def receive_to_eof(sock):
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    def test_opaque_bytes_and_bidirectional_half_close(self):
        client, peer, upstream, remote = self.sockets()
        errors = []

        def run():
            try:
                egress.relay_tunnel(client, upstream, idle_timeout=0.5, lifetime=2)
            except Exception as error:
                errors.append(type(error).__name__)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        payload = b"\x00\xffopaque-tls" * 6000
        writer_errors = []

        def write_request():
            try:
                peer.sendall(payload)
                peer.shutdown(socket.SHUT_WR)
            except OSError as error:
                writer_errors.append(type(error).__name__)

        # Drain concurrently: some hosts have very small socketpair buffers.
        writer = threading.Thread(target=write_request, daemon=True)
        writer.start()
        self.assertEqual(self.receive_to_eof(remote), payload)
        writer.join(1)
        self.assertFalse(writer.is_alive())
        self.assertEqual(writer_errors, [])
        remote.sendall(b"reply-after-request-eof\x00\xff")
        remote.shutdown(socket.SHUT_WR)
        self.assertEqual(self.receive_to_eof(peer), b"reply-after-request-eof\x00\xff")
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual((client.fileno(), upstream.fileno()), (-1, -1))

    def test_idle_limit_closes_both_sockets(self):
        client, _, upstream, _ = self.sockets()
        with self.assertRaises(TimeoutError):
            egress.relay_tunnel(client, upstream, idle_timeout=0.03, lifetime=1)
        self.assertEqual((client.fileno(), upstream.fileno()), (-1, -1))

    def test_lifetime_is_independent_of_idle_limit(self):
        client, _, upstream, _ = self.sockets()
        with mock.patch.object(egress.time, "monotonic", side_effect=[0.0, 0.0, 0.03]), \
                mock.patch.object(egress.select, "select", return_value=([], [], [])) as wait:
            with self.assertRaises(TimeoutError):
                egress.relay_tunnel(client, upstream, idle_timeout=1, lifetime=0.03)
        wait.assert_called_once()
        self.assertAlmostEqual(wait.call_args.args[3], 0.03)
        self.assertEqual((client.fileno(), upstream.fileno()), (-1, -1))

    def test_one_close_error_does_not_skip_other_socket(self):
        client, upstream = MemorySocket(), MemorySocket()
        client.close = mock.Mock(side_effect=OSError("private close details"))
        with self.assertRaises(TimeoutError):
            egress.relay_tunnel(client, upstream, lifetime=0)
        client.close.assert_called_once()
        self.assertTrue(upstream.closed)

    def test_forwarding_write_error_closes_both(self):
        client, upstream = MemorySocket(b"opaque"), MemorySocket()
        upstream.sendall = mock.Mock(side_effect=OSError("private write details"))
        with mock.patch.object(egress.select, "select", return_value=([client], [], [])):
            with self.assertRaises(OSError):
                egress.relay_tunnel(client, upstream)
        self.assertTrue(client.closed and upstream.closed)
        upstream.sendall.assert_called_once_with(b"opaque")


class ServerTests(unittest.TestCase):
    def server(self):
        with mock.patch.object(socketserver.TCPServer, "__init__", return_value=None):
            return egress.EgressServer(("127.0.0.1", 0))

    def test_bounded_admission_returns_fixed_503_and_no_thread(self):
        server = self.server()
        for _ in range(egress.MAX_CONNECTIONS):
            self.assertTrue(server._slots.acquire(blocking=False))
        client = MemorySocket()
        with mock.patch.object(socketserver.ThreadingMixIn, "process_request") as start:
            server.process_request(client, ("local", 0))
            start.assert_not_called()
        self.assertTrue(client.sent.startswith(b"HTTP/1.1 503 Service Unavailable\r\n"))
        self.assertIn(b"Content-Length: 0\r\n", client.sent)
        self.assertTrue(client.closed)

    def test_thread_start_failure_releases_admission(self):
        server = self.server()
        with mock.patch.object(socketserver.ThreadingMixIn, "process_request", side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):
                server.process_request(MemorySocket(), ("local", 0))
        acquired = [server._slots.acquire(blocking=False) for _ in range(egress.MAX_CONNECTIONS + 1)]
        self.assertEqual(acquired, [True] * egress.MAX_CONNECTIONS + [False])

    def test_worker_failure_releases_admission(self):
        server = self.server()
        server._slots.acquire()
        with mock.patch.object(socketserver.ThreadingMixIn, "process_request_thread", side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):
                server.process_request_thread(MemorySocket(), ("local", 0))
        acquired = [server._slots.acquire(blocking=False) for _ in range(egress.MAX_CONNECTIONS + 1)]
        self.assertEqual(acquired, [True] * egress.MAX_CONNECTIONS + [False])

    def test_exact_safe_cli_flags(self):
        with mock.patch.object(egress, "EgressServer") as server:
            egress.main(["--host", "127.0.0.1", "--port", "3128"])
        server.assert_called_once_with(("127.0.0.1", 3128))
        server.return_value.__enter__.return_value.serve_forever.assert_called_once()

    def test_no_dynamic_allowlist_or_insecure_cli(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit), mock.patch.object(egress, "EgressServer") as server:
                egress.main(["--allow-host", "127.0.0.1"])
            server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
