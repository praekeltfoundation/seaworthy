import pytest

from seaworthy.checks import docker_available


def dockertest():
    """
    Skip tests that require docker to be available.

    This is a function that returns a decorator so that we don't run arbitrary
    docker client code on import. Unlike ``seaworthy.checks.dockertest``, this
    implementation doesn't require ``unittest.TestCase``. It does, however,
    require pytest.
    """
    return pytest.mark.skipif(
        not docker_available(), reason='Docker not available.')
