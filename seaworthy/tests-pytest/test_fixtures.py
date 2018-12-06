import docker

import pytest

from seaworthy.checks import docker_client
from seaworthy.definitions import (
    ContainerDefinition, NetworkDefinition, VolumeDefinition)
from seaworthy.helpers import DockerHelper, fetch_images
from seaworthy.pytest.checks import dockertest
from seaworthy.pytest.fixtures import (
    clean_container_fixtures, docker_helper_fixture, image_fetch_fixture,
    resource_fixture)


# FIXME 2018-12-06: https://github.com/praekeltfoundation/seaworthy/issues/84
pytestmark = pytest.mark.skipif(int(pytest.__version__.split('.')[0]) >= 4,
                                reason='tests incompatible with pytest 4')


IMG = 'nginx:alpine'


def setup_module():
    with docker_client() as client:
        fetch_images(client, [IMG])


# We redefine the docker_helper fixture here to have function scope so our
# tests don't conflict.
docker_helper = docker_helper_fixture(scope='function')


@dockertest()
class TestDockerHelperFixture:
    def test_setup_teardown(self):
        """
        The fixture should yield a setup helper, and afterwards tear down the
        helper.
        """
        fixture_gen = docker_helper()
        helper = next(fixture_gen)
        assert isinstance(helper, DockerHelper)

        # Test we can create a container; if we can the helper must be set
        # up
        container = helper.containers.create('test', IMG)

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        with pytest.raises(docker.errors.NotFound):
            container.reload()


@dockertest()
class TestImageFetchFixtureFunc:
    def test_create_fixture(self, docker_helper):
        """
        We can create an fixture that fetches an image and returns an image
        model.
        """
        fixture = image_fetch_fixture(IMG, name='image', scope='module')
        image = fixture(docker_helper)

        assert isinstance(image, docker.models.images.Image)
        assert IMG in image.tags


# Dependent fixtures for use in TestResourceFixtureFunc::test_dependencies
volume = VolumeDefinition('test')
volume_fixture = resource_fixture(volume, 'volume_test')
network = NetworkDefinition('test')
network_fixture = resource_fixture(network, 'network_test')


@dockertest()
class TestResourceFixtureFunc:
    def test_setup_teardown(self, request, docker_helper):
        """
        The fixture should yield a started container, and afterwards stop and
        remove the container.
        """
        fixture = resource_fixture(
            ContainerDefinition(name='test', image=IMG), 'test')
        fixture_gen = fixture(request, docker_helper)
        container = next(fixture_gen)

        assert isinstance(container, ContainerDefinition)
        assert container.inner().status == 'running'

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        # Container has been stopped and removed
        assert not container.created

    def test_dependencies(self, request, docker_helper):
        """
        When the fixture depends on other fixtures, those fixtures should be
        setup when the fixture is used.
        """
        container_fixture = resource_fixture(
            ContainerDefinition(name='test', image=IMG), 'container_test',
            dependencies=('volume_test', 'network_test'))
        fixture_gen = container_fixture(request, docker_helper)
        container = next(fixture_gen)

        assert isinstance(container, ContainerDefinition)
        assert container.status() == 'running'
        assert volume.created
        assert network.created

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        # Container has been stopped and removed
        assert not container.created
        # Can't assert dependent fixture teardown--only happens once test
        # method returns


@dockertest()
class TestCleanContainerFixturesFunc:
    def test_setup_teardown(self, request, docker_helper):
        """
        The fixture should yield a started container, and afterwards stop and
        remove the container.
        """
        raw_fixture, fixture = clean_container_fixtures(
            ContainerDefinition(name='test', image=IMG), 'test')
        fixture_gen = raw_fixture(request, docker_helper)
        # TODO: Assert on cleaning fixture
        container = next(fixture_gen)

        assert isinstance(container, ContainerDefinition)
        assert container.inner().status == 'running'

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        # Container has been stopped and removed
        assert not container.created


@dockertest()
class PytestFixtureMixin:
    def make_definition(self, name):
        raise NotImplementedError()  # pragma: no cover

    def test_setup_teardown(self, request, docker_helper):
        """
        The ``pytest_fixture()`` method should return a fixture. That fixture
        should yield the definition with its resource created and when yielded
        again, the resource should be removed.
        """
        fixture = self.make_definition('test').pytest_fixture('test')
        fixture_gen = fixture(request, docker_helper)
        definition = next(fixture_gen)

        # Resource has been created
        assert definition.created

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        # Resource has been removed
        assert not definition.created


class TestContainerDefinition(PytestFixtureMixin):
    def make_definition(self, name):
        return ContainerDefinition(name, IMG)

    def test_clean_fixtures(self, request, docker_helper):
        """
        The fixture returned by the ``pytest_clean_fixture()`` method should
        yield a started container, and afterwards stop and remove the
        container.
        """
        raw_fixture, fixture = ContainerDefinition(
            name='test', image=IMG).pytest_clean_fixtures('test')
        fixture_gen = raw_fixture(request, docker_helper)
        # TODO: Assert on cleaning fixture
        container = next(fixture_gen)

        assert isinstance(container, ContainerDefinition)
        assert container.inner().status == 'running'

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        # Container has been stopped and removed
        assert not container.created


class TestNetworkDefinition(PytestFixtureMixin):
    def make_definition(self, name):
        return NetworkDefinition(name)


class TestVolumeDefinition(PytestFixtureMixin):
    def make_definition(self, name):
        return VolumeDefinition(name)
