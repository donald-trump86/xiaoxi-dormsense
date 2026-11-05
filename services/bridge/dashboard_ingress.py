#!/usr/bin/env python3
"""Opaque TCP ingress for the existing Hermes dashboard, fixed to hermes:9119.

DNS uses the system resolver without a hard wall-clock deadline. All returned
addresses must be native RFC1918 or ULA before any numeric connection attempt.
The existing bounded admission and relay retain their I/O, idle and lifetime
limits. The relay does not parse HTTP, inspect credentials, or terminate TLS.
"""

import argparse
import ipaddress
import socket
import socketserver
import time

from inference_egress import (
    CONNECT_ATTEMPT_TIMEOUT,
    EgressServer,
    IO_TIMEOUT,
    MAX_DNS_RESULTS,
    close_sockets,
    relay_tunnel,
)

DASHBOARD_HOST = "hermes"
DASHBOARD_PORT = 9119
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
))


class IngressError(Exception):
    pass


def is_dashboard_address(text: str) -> bool:
    if not isinstance(text, str) or "%" in text:
        return False
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    return any(address in network for network in PRIVATE_NETWORKS)


def resolve_dashboard() -> list[tuple[int, tuple]]:
    try:
        answers = socket.getaddrinfo(
            DASHBOARD_HOST, DASHBOARD_PORT,
            type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except OSError:
        raise IngressError("dashboard_unavailable") from None
    if not isinstance(answers, list) or not 0 < len(answers) <= MAX_DNS_RESULTS:
        raise IngressError("dashboard_unavailable")
    addresses = []
    for answer in answers:
        if not isinstance(answer, tuple) or len(answer) != 5:
            raise IngressError("dashboard_unavailable")
        family, kind, protocol, _, address = answer
        if (not all(isinstance(value, int) and not isinstance(value, bool)
                    for value in (family, kind, protocol))
                or family not in (socket.AF_INET, socket.AF_INET6)
                or kind != socket.SOCK_STREAM or protocol != socket.IPPROTO_TCP
                or not isinstance(address, tuple)
                or len(address) != (2 if family == socket.AF_INET else 4)):
            raise IngressError("dashboard_unavailable")
        if (type(address[1]) is not int or address[1] != DASHBOARD_PORT
                or not is_dashboard_address(address[0])):
            raise IngressError("dashboard_unavailable")
        parsed = ipaddress.ip_address(address[0])
        if ((family == socket.AF_INET) != (parsed.version == 4)
                or (family == socket.AF_INET6 and any(
                    type(value) is not int or value != 0 for value in address[2:]))):
            raise IngressError("dashboard_unavailable")
        pinned = ((str(parsed), DASHBOARD_PORT) if parsed.version == 4
                  else (str(parsed), DASHBOARD_PORT, 0, 0))
        item = (family, pinned)
        if item not in addresses:
            addresses.append(item)
    return sorted(addresses, key=lambda item: item[0] != socket.AF_INET)


def connect_dashboard() -> socket.socket:
    addresses = resolve_dashboard()
    deadline = time.monotonic() + IO_TIMEOUT
    for family, address in addresses:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        upstream = None
        connected = False
        try:
            upstream = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            upstream.settimeout(min(CONNECT_ATTEMPT_TIMEOUT, remaining))
            upstream.connect(address)
            upstream.settimeout(IO_TIMEOUT)
            connected = True
            return upstream
        except OSError:
            pass
        finally:
            if not connected:
                close_sockets(upstream)
    raise IngressError("dashboard_unavailable")


class DashboardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        upstream = None
        try:
            upstream = connect_dashboard()
            relay_tunnel(self.request, upstream)
        except Exception:
            pass
        finally:
            close_sockets(self.request, upstream)


class DashboardIngressServer(EgressServer):
    def __init__(self, server_address: tuple[str, int]):
        super().__init__(server_address)
        self.RequestHandlerClass = DashboardHandler


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9119)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    with DashboardIngressServer((args.host, args.port)) as server:
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
