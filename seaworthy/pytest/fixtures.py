"""
A number of pytest fixtures or factories for fixtures.
"""

import os

import pytest

from seaworthy.helpers import DockerHelper


def docker_helper_fixture(name='docker_helper', scope='module', **kwargs):
    """
    Create a fixture for :class:`~seaworthy.DockerHelper`.

    This can be used to create a fixture with a different name to the default.
    It can also be used to override the scope of the default fixture::

        docker_helper = docker_helper_fixture(scope='class')

    :param name: The name of the fixture.
    :param scope: The scope of the fixture.
    :param kwargs:
        Keyword arguments to pass to the :class:`~seaworthy.DockerHelper`
        constructor.
    """
    @pytest.fixture(name=name, scope=scope)
    def fixture():
        namespace = kwargs.pop('namespace', 'test')
        if 'PYTEST_XDIST_WORKER' in os.environ:  # pragma: no cover
            namespace = '{}_{}'.format(
                namespace, os.environ['PYTEST_XDIST_WORKER'])
        docker_helper = DockerHelper(namespace=namespace, **kwargs)
        yield docker_helper
        docker_helper.teardown()
    return fixture


#: Default fixture for :class:`~seaworthy.DockerHelper`. Has module scope.
docker_helper = docker_helper_fixture()


def image_fetch_fixture(image, name, scope='module'):
    """
    Create a fixture to fetch an image.
    """
    @pytest.fixture(name=name, scope=scope)
    def fixture(docker_helper):
        return docker_helper.images.fetch(image)
    return fixture


def resource_fixture(definition, name, scope='function'):
    """
    Create a fixture for a resource.

    .. note:: This function returns a fixture function. It is important to keep
        a reference to the returned function within the scope of the tests that
        use the fixture.

    .. code-block:: python

        fixture = resource_fixture(PostgreSQLContainer(), 'postgresql')

        def test_container(postgresql):
            \"""Test something about the PostgreSQL container...\"""

    :param definition:
        A resource definition, one of those defined in the
        :mod:`seaworthy.definitions` module.
    :param name: The fixture name.
    :param scope: The scope of the fixture.

    :returns: The fixture function.
    """
    @pytest.fixture(name=name, scope=scope)
    def fixture(docker_helper):
        definition.setup(helper=docker_helper)
        yield definition
        definition.teardown()

    return fixture


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

    .. note:: This function returns two fixture functions. It is important to
        keep references to the returned functions within the scope of the tests
        that use the fixtures.

    .. code-block:: python

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
        A "container" object that is a subclass of
        :class:`.ContainerDefinition`.
    :param name:
        The fixture name.
    :param scope:
        The scope of the fixture.

    :returns:
        A tuple of two fixture functions.
    """
    raw_name = 'raw_{}'.format(name)
    return (resource_fixture(container, raw_name, scope),
            _clean_container_fixture(name, raw_name))


__all__ = ['clean_container_fixtures', 'docker_helper',
           'docker_helper_fixture', 'image_fetch_fixture', 'resource_fixture']
