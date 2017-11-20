"""
Checks and test decorators for skipping tests that require Docker to be
present.
"""

import unittest
from contextlib import contextmanager

import docker

from requests.exceptions import ConnectionError


@contextmanager
def docker_client():
    """
    A context manager that creates and cleans up a Docker API client.

    In most cases, it's better to use :class:`~seaworthy.helpers.DockerHelper`
    instead.
    """
    client = docker.client.from_env()
    yield client
    client.api.close()


def docker_available():
    """
    Check if Docker is available and responsive.
    """
    with docker_client() as client:
        try:
            return client.ping()
        except ConnectionError:  # pragma: no cover
            return False


def dockertest():
    """
    Skip tests that require Docker to be available.

    This is a function that returns a decorator so that we don't run arbitrary
    Docker client code on import. This implementation only works with tests
    based on :class:`unittest.TestCase`. If you're using pytest, you probably
    want :func:`seaworthy.pytest.dockertest` instead.
    """
    return unittest.skipUnless(docker_available(), 'Docker not available.')
