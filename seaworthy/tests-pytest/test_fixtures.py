import docker
import pytest

from seaworthy.checks import docker_client
from seaworthy.containers.base import ContainerBase
from seaworthy.dockerhelper import DockerHelper, fetch_images
from seaworthy.pytest.checks import dockertest
from seaworthy.pytest.fixtures import (
    clean_container_fixtures, container_fixture, docker_helper_fixture,
    image_pull_fixture)


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
class TestImagePullFixtureFunc:
    def test_create_fixture(self, docker_helper):
        """
        We can create an fixture that pulls an image and returns an image
        model.
        """
        fixture = image_pull_fixture(IMG, name='image', scope='module')
        image = fixture(docker_helper)

        assert isinstance(image, docker.models.images.Image)
        assert IMG in image.tags


@dockertest()
class TestContainerFixtureFunc:
    def test_setup_teardown(self, docker_helper):
        """
        The fixture should yield a started container, and afterwards stop and
        remove the container.
        """
        fixture = container_fixture(
            ContainerBase(name='test', image=IMG), 'test')
        fixture_gen = fixture(docker_helper)
        container = next(fixture_gen)

        assert isinstance(container, ContainerBase)
        assert container.inner().status == 'running'

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        # Container has been stopped and removed
        with pytest.raises(RuntimeError):
            container.inner()


@dockertest()
class TestCleanContainerFixturesFunc:
    def test_setup_teardown(self, docker_helper):
        """
        The fixture should yield a started container, and afterwards stop and
        remove the container.
        """
        raw_fixture, fixture = clean_container_fixtures(
            ContainerBase(name='test', image=IMG), 'test')
        fixture_gen = raw_fixture(docker_helper)
        # TODO: Assert on cleaning fixture
        container = next(fixture_gen)

        assert isinstance(container, ContainerBase)
        assert container.inner().status == 'running'

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        # Container has been stopped and removed
        with pytest.raises(RuntimeError):
            container.inner()
