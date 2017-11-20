"""
pytest mark to skip tests that require Docker.
"""

import pytest

from seaworthy.checks import docker_available


def dockertest():
    """
    Skip tests that require Docker to be available.

    This is a function that returns a decorator so that we don't run arbitrary
    Docker client code on import. Unlike :func:`seaworthy.checks.dockertest`,
    this implementation doesn't require :class:`unittest.TestCase`. It does,
    however, require pytest.
    """
    return pytest.mark.skipif(
        not docker_available(), reason='Docker not available.')
