"""
This is a module for horrible low-level things that we really wish we
didn't have to build and maintain ourselves.
"""

import socket
import struct
import time
from contextlib import contextmanager

from urllib3.exceptions import ReadTimeoutError


# We want time.monotonic on Pythons that have it, otherwise time.time will have
# to do.
get_time = getattr(time, 'monotonic', time.time)


class SocketClosed(Exception):
    """
    Exception used for flow control. :-(
    """


def stream_logs(container, stdout=True, stderr=True, tail='all', timeout=10.0):
    """
    Stream logs from a Docker container within a timeout.

    We can't use docker-py's existing streaming support because that's stuck
    behind a blocking API and we have no (sane) way to enforce a timeout.
    """
    deadline = get_time() + timeout

    with _haxxed_mrsh(container):
        resp, sock = container.logs(
            stdout=stdout, stderr=stderr, stream=True, tail=tail, follow=True)
    try:
        while True:
            try:
                yield read_frame(resp, sock, deadline)
            except SocketClosed:
                return
    finally:
        # We also need to close the response object to avoid leaking any
        # resources.
        resp.close()


@contextmanager
def _haxxed_mrsh(container):
    """
    This temporarily monkey-patches the Docker API client's
    _multiplexed_response_stream_helper method so we can get the raw socket and
    do our own timeout-enabled streaming.
    """
    api = container.client.api

    def _mrsh(response):
        return response, api._get_raw_response_socket(response)._sock

    _orig_mrsh = api._multiplexed_response_stream_helper
    try:
        api._multiplexed_response_stream_helper = _mrsh
        yield container
    finally:
        api._multiplexed_response_stream_helper = _orig_mrsh


def read_by_deadline(resp, sock, deadline, n):
    """
    Read up to N bytes from a socket. If there's nothing to read, signal that
    it's closed.
    """
    time_left = deadline - get_time()
    # Avoid past-deadline special cases by setting a small timeout instead.
    sock.settimeout(max(time_left, 0.001))
    try:
        data = resp.raw.read(n)
    except (ReadTimeoutError, socket.timeout) as e:
        raise TimeoutError('Timeout waiting for container logs.')
    if len(data) == 0:
        raise SocketClosed()
    return data


def read_n_bytes(resp, sock, n, deadline):
    """
    Read exactly N bytes from a socket before a timeout deadline. We assume
    that the selector contains exactly one socket.
    """
    buf = b''
    while len(buf) < n:
        buf += read_by_deadline(resp, sock, deadline, n - len(buf))
    return buf


def read_frame(resp, sock, deadline):
    """
    Read a Docker stream frame before a timeout deadline.
    """
    header = read_n_bytes(resp, sock, 8, deadline)
    _, size = struct.unpack('>BxxxL', header)
    return read_n_bytes(resp, sock, size, deadline)
