"""
This is a module for horrible low-level things that we really wish we
didn't have to build and maintain ourselves.
"""

import select
import struct
from datetime import datetime, timedelta


class SocketClosed(Exception):
    """
    Exception used for flow control. :-(
    """


def stream_logs(container, stdout=1, stderr=1, stream=1, timeout=10.0):
    deadline = datetime.now() + timedelta(seconds=timeout)
    params = {
        'stdout': 1 if stdout else 0,
        'stderr': 1 if stderr else 0,
        'stream': 1 if stream else 0,
        'logs': 1,
    }
    sock = container.attach_socket(params=params)._sock
    sock.setblocking(False)  # Make the socket nonblocking.
    while True:
        try:
            yield read_frame(sock, deadline)
        except SocketClosed:
            return


def read_n_bytes(sock, n, deadline):
    """
    Read exactly N bytes from a socket before a timeout deadline.
    """
    buf = b''
    while datetime.now() < deadline:
        r, _, _ = select.select([sock], [], [], 0.01)
        if r:
            data = sock.recv(n - len(buf))
            if len(data) == 0:
                # Socket is readable, but has no data waiting. This means it's
                # closed, so we're done.
                raise SocketClosed()
            buf += data
        if len(buf) == n:
            return buf
    raise TimeoutError('Timeout waiting for container logs.')


def read_frame(sock, deadline):
    """
    Read a docker stream frame before a timeout deadline.
    """
    header = read_n_bytes(sock, 8, deadline)
    _, size = struct.unpack('>BxxxL', header)
    return read_n_bytes(sock, size, deadline)
