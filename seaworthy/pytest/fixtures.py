"""
Contains a number of pytest fixtures or factories for fixtures.

To us this module, import the fixtures in your tests.::

    from seaworthy.pytest.fixtures import *  # noqa: F401,F403
"""

import pytest

from seaworthy.dockerhelper import DockerHelper


@pytest.fixture(scope='module')
def docker_helper():
    """
    Default fixture for the ``DockerHelper``. Has module scope.
    """
    docker_helper = DockerHelper()
    docker_helper.setup()
    yield docker_helper
    docker_helper.teardown()


def container_fixture(container, name, scope='function'):
    """
    Create a fixture for a container.

    Note that it is important to keep a reference to the fixture function
    returned by this function::

        fixture = container_fixture(PostgreSQLContainer(), 'postgresql')

        def test_container(postgresql):
            \"""Test something about the PostgreSQL container...\"""

    :param container:
        A "container" object that is a subtype of
        ~seaworthy.containers.ContainerBase.
    :param name: The fixture name.
    :param scope: The scope of the fixture.

    :returns: The fixture function.
    """
    @pytest.fixture(name=name, scope=scope)
    def raw_fixture(docker_helper):
        container.create_and_start(docker_helper)
        yield container
        container.stop_and_remove(docker_helper)

    return raw_fixture


def _clean_container_fixture(name, raw_name):
    @pytest.fixture(name=name)
    def clean_fixture(request):
        container = request.getfixturevalue(raw_name)
        if 'clean_{}'.format(name) in request.keywords:
            container.clean()
        return container

    return clean_fixture


def clean_container_fixtures(container, name, scope='class'):
    """
    Creates a fixture for a container that can be "cleaned". When a code block
    is marked with ``@pytest.mark.clean_<fixture name>`` then the ``clean``
    method will be called on the container object before it is passed as an
    argument to the test function.

    Note that this function returns two fixture functions and references must
    be kept to both in the correct scope.::

        f1, f2 = clean_container_fixtures(PostgreSQLContainer(), 'postgresql')

        class TestPostgresqlContainer
            @pytest.mark.clean_postgresql
            def test_clean_container(self, web_container, postgresql):
                \"""
                Test something about the container that requires it to have a
                clean state (e.g. database table creation).
                \"""

            def test_dirty_container(self, web_container, postgresql):
                \"""
                Test something about the container that doesn't require it to
                have a clean state (e.g. testing something about a dependent
                container).
                \"""

    :param container:
        A "container" object that is a subtype of
        ~seaworthy.containers.ContainerBase.
    :param name:
        The fixture name.
    :param scope:
        The scope of the fixture.

    :returns:
        A tuple of two fixture functions.
    """
    raw_name = 'raw_{}'.format(name)
    return (container_fixture(container, raw_name, scope),
            _clean_container_fixture(name, raw_name))


__all__ = ['container_fixture', 'docker_helper']
