"""
This module contains some checks and test decorators for skipping tests
that require docker to be present.
"""

import unittest

import docker


def docker_available():
    try:
        return docker.client.from_env().ping()
    except:
        return False


def dockertest():
    """
    Skip tests that require docker to be available.

    This is a function that returns a decorator so that we don't run arbitrary
    docker client code on import. This implementation only works with tests
    based on ``unittest.TestCase``. If you're using pytest, you probably want
    ``seaworthy.pytest.dockertest`` instead.
    """
    return unittest.skipUnless(docker_available(), 'Docker not available.')
