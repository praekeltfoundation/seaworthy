from docker.errors import NotFound
import pytest

from seaworthy.checks import docker_client
from seaworthy.containers import ContainerBase
from seaworthy.dockerhelper import DockerHelper
from seaworthy.pytest import dockertest
from seaworthy.pytest.fixtures import (
    clean_container_fixtures, container_fixture, docker_helper)


IMG = 'nginx:alpine'


@dockertest()
class TestDockerHelperFixture:
    def test_setup_teardown(self):
        fixture_gen = docker_helper()
        helper = next(fixture_gen)
        assert isinstance(helper, DockerHelper)

        # Test we can create a container; if we can the helper must be set
        # up
        container = helper.create_container('test', IMG)

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        with docker_client() as client:
            with pytest.raises(NotFound):
                client.containers.get(container.id)


class CleanableContainer(ContainerBase):
    def __init__(self):
        super().__init__(name='test', image=IMG, wait_matchers=[])
        self.cleaned = False

    def clean(self):
        self.cleaned = True


fixture = container_fixture(CleanableContainer(), 'container')


@dockertest()
class TestContainerFixtureFunc:
    def test_fixture(self, container):
        assert isinstance(container, CleanableContainer)

        inner = container.container()
        assert inner.status == 'running'


f1, f2 = clean_container_fixtures(
    CleanableContainer(), 'cleanable', scope='function')


@dockertest()
class TestCleanContainerFixturesFunc:
    def test_dirty(self, cleanable):
        assert not cleanable.cleaned

    @pytest.mark.clean_cleanable
    def test_clean(self, cleanable):
        assert cleanable.cleaned
