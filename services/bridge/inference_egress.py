#!/usr/bin/env python3
"""Fixed-destination CONNECT egress; TLS remains opaque and client-verified.

DNS uses the system resolver and has no hard wall-clock deadline. All returned
addresses pass a conservative, version-independent guard before any connection.
There are no proxy credentials, dynamic destinations, or deployment test bypasses.
"""

import argparse
import ipaddress
import re
import select
import socket
import socketserver
import threading
import time

ALLOWED_HOSTS = frozenset({
    "inference-api.nousresearch.com", "portal.nousresearch.com",
    "api.deepseek.com", "speech.platform.bing.com", "api.msedgeservices.com",
    "weather.cma.cn", "whois.pconline.com.cn",
})
MAX_CONNECTIONS = 16
MAX_DNS_RESULTS = 16
MAX_REQUEST_LINE = 2048
MAX_HEADER_BYTES = 16384
MAX_HEADERS = 50
MAX_CHUNK = 65536
IO_TIMEOUT = 5.0
CONNECT_ATTEMPT_TIMEOUT = 2.0
IDLE_TIMEOUT = 120.0
TUNNEL_LIFETIME = 900.0
HEADER_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")

# Include globally marked special-purpose ranges whose classification differs
# among supported Python versions. A broader rejection is preferable to routing
# through protocol anycast, documentation, or transition addresses.
V4_SPECIAL = tuple(ipaddress.ip_network(value) for value in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
    "192.31.196.0/24", "192.52.193.0/24", "192.88.99.0/24",
    "192.168.0.0/16", "192.175.48.0/24", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
))
V6_UNICAST = ipaddress.ip_network("2000::/3")
V6_SPECIAL = tuple(ipaddress.ip_network(value) for value in (
    "2001::/23", "2001:db8::/32", "2002::/16", "2620:4f:8000::/48",
    "3ffe::/16", "3fff::/20",
))
REASONS = {
    200: "Connection Established", 400: "Bad Request", 403: "Forbidden",
    405: "Method Not Allowed", 408: "Request Timeout",
    431: "Request Header Fields Too Large", 502: "Bad Gateway",
    503: "Service Unavailable",
}


class ProxyError(Exception):
    """Only a fixed status may cross the request error boundary."""

    def __init__(self, status: int):
        self.status = status
        super().__init__("proxy_rejected")


def close_sockets(*peers: socket.socket | None) -> None:
    for peer in peers:
        if peer is not None:
            try:
                peer.close()
            except OSError:
                pass


def send_response(client: socket.socket, status: int) -> None:
    response = f"HTTP/1.1 {status} {REASONS[status]}\r\nCache-Control: no-store\r\n"
    if status != 200:
        response += "Content-Length: 0\r\nConnection: close\r\n"
    client.settimeout(IO_TIMEOUT)
    client.sendall((response + "\r\n").encode("ascii"))


def read_connect_request(client: socket.socket, deadline: float) -> str:
    """Consume exactly the headers, leaving any tunnel bytes on the socket."""
    data = bytearray()
    try:
        while not data.endswith(b"\r\n\r\n"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProxyError(408)
            client.settimeout(min(IO_TIMEOUT, remaining))
            byte = client.recv(1)
            if not byte:
                raise ProxyError(400)
            if byte == b"\n" and (not data or data[-1] != 13):
                raise ProxyError(400)
            data += byte
            if len(data) > MAX_HEADER_BYTES:
                raise ProxyError(431)
            if b"\r\n" not in data and len(data) > MAX_REQUEST_LINE:
                raise ProxyError(431)
    except TimeoutError:
        raise ProxyError(408) from None
    lines = bytes(data[:-4]).split(b"\r\n")
    if len(lines[0]) > MAX_REQUEST_LINE or len(lines) - 1 > MAX_HEADERS:
        raise ProxyError(431)
    parts = lines[0].split(b" ")
    if len(parts) != 3 or parts[2] not in (b"HTTP/1.0", b"HTTP/1.1"):
        raise ProxyError(400)
    if parts[0] != b"CONNECT":
        raise ProxyError(405)
    targets = {f"{host}:443".encode("ascii"): host for host in ALLOWED_HOSTS}
    host = targets.get(parts[1])
    if host is None:
        raise ProxyError(403)
    host_header = None
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator or HEADER_NAME.fullmatch(name) is None:
            raise ProxyError(400)
        if any(byte != 9 and not 32 <= byte <= 126 for byte in value):
            raise ProxyError(400)
        name = name.lower()
        if name in (b"content-length", b"transfer-encoding", b"expect", b"trailer"):
            raise ProxyError(400)
        if name == b"host":
            if host_header is not None:
                raise ProxyError(400)
            host_header = value.strip(b" \t")
            if host_header not in (parts[1], host.encode("ascii")):
                raise ProxyError(400)
    if parts[2] == b"HTTP/1.1" and host_header is None:
        raise ProxyError(400)
    return host


def is_public_address(text: str) -> bool:
    if not isinstance(text, str) or "%" in text:
        return False
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return not any(address in network for network in V4_SPECIAL)
    return (address in V6_UNICAST
            and not any(address in network for network in V6_SPECIAL))


def resolve_addresses(host: str) -> list[tuple[int, tuple]]:
    """Validate the complete fresh answer, then prefer native IPv4."""
    if host not in ALLOWED_HOSTS:
        raise ProxyError(403)
    try:
        answers = socket.getaddrinfo(
            host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except OSError:
        raise ProxyError(502) from None
    if not answers or len(answers) > MAX_DNS_RESULTS:
        raise ProxyError(502)
    addresses = []
    for answer in answers:
        if not isinstance(answer, tuple) or len(answer) != 5:
            raise ProxyError(502)
        family, kind, protocol, _, sockaddr = answer
        if (family not in (socket.AF_INET, socket.AF_INET6)
                or kind != socket.SOCK_STREAM or protocol != socket.IPPROTO_TCP
                or not isinstance(sockaddr, tuple)
                or len(sockaddr) != (2 if family == socket.AF_INET else 4)):
            raise ProxyError(502)
        if (type(sockaddr[1]) is not int or sockaddr[1] != 443
                or not is_public_address(sockaddr[0])):
            raise ProxyError(502)
        address = ipaddress.ip_address(sockaddr[0])
        if ((family == socket.AF_INET) != (address.version == 4)
                or (family == socket.AF_INET6 and any(
                    type(value) is not int or value != 0 for value in sockaddr[2:]))):
            raise ProxyError(502)
        pinned = ((str(address), 443) if family == socket.AF_INET
                  else (str(address), 443, 0, 0))
        item = (family, pinned)
        if item not in addresses:
            addresses.append(item)
    return sorted(addresses, key=lambda item: item[0] != socket.AF_INET)


def connect_upstream(host: str) -> socket.socket:
    addresses = resolve_addresses(host)
    deadline = time.monotonic() + IO_TIMEOUT
    for family, sockaddr in addresses:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        upstream = None
        try:
            upstream = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            upstream.settimeout(min(CONNECT_ATTEMPT_TIMEOUT, remaining))
            upstream.connect(sockaddr)
            upstream.settimeout(IO_TIMEOUT)
            return upstream
        except OSError:
            close_sockets(upstream)
    raise ProxyError(502)


def relay_tunnel(client: socket.socket, upstream: socket.socket, *,
                 idle_timeout: float = IDLE_TIMEOUT,
                 lifetime: float = TUNNEL_LIFETIME) -> None:
    """Relay opaque bounded chunks, propagate half-closes, and close both ends."""
    started = last_activity = time.monotonic()
    readers = {client: upstream, upstream: client}

    def budget() -> float:
        now = time.monotonic()
        remaining = min(IO_TIMEOUT, started + lifetime - now,
                        last_activity + idle_timeout - now)
        if remaining <= 0:
            raise TimeoutError("tunnel_timeout")
        return remaining

    try:
        while readers:
            ready, _, _ = select.select(list(readers), [], [], budget())
            for source in ready:
                destination = readers[source]
                source.settimeout(budget())
                chunk = source.recv(MAX_CHUNK)
                if not chunk:
                    del readers[source]
                    destination.shutdown(socket.SHUT_WR)
                    continue
                destination.settimeout(budget())
                destination.sendall(chunk)
                last_activity = time.monotonic()
    finally:
        close_sockets(client, upstream)


class EgressHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        upstream = None
        established = False
        try:
            host = read_connect_request(self.request, time.monotonic() + IO_TIMEOUT)
            upstream = connect_upstream(host)
            established = True
            send_response(self.request, 200)
            relay_tunnel(self.request, upstream)
        except Exception as error:
            if not established:
                status = error.status if isinstance(error, ProxyError) else 502
                try:
                    send_response(self.request, status)
                except OSError:
                    pass
        finally:
            close_sockets(self.request, upstream)


class EgressServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, server_address: tuple[str, int]):
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(server_address, EgressHandler)

    def process_request(self, request, client_address) -> None:
        if not self._slots.acquire(blocking=False):
            try:
                send_response(request, 503)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address) -> None:
        # Never print untrusted request contents, exception details, or secrets.
        pass


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3128)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    with EgressServer((args.host, args.port)) as server:
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
