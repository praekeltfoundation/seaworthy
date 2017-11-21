import pytest

from seaworthy.checks import docker_client
from seaworthy.definitions import (
    ContainerDefinition, NetworkDefinition, VolumeDefinition)
from seaworthy.helpers import fetch_image
from seaworthy.pytest import dockertest

IMG = 'nginx:alpine'


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

        # Resrouce has been created
        assert definition.created

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        # Resource has been removed
        assert not definition.created


class TestContainerDefinition(PytestFixtureMixin):
    @classmethod
    def setUpClass(cls):
        with docker_client() as client:
            fetch_image(client, IMG)

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
