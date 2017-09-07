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
    def test_fixture(self, testdir):
        """
        The ``docker_helper`` fixture should automatically be in scope for a
        project that uses this pytest plugin.  When the ``DockerHelper`` is
        passed to a test function using a fixture, it should be possible to
        create, start, stop, and remove a container using the helper.
        """
        testdir.makepyfile("""
            from docker.errors import NotFound
            import pytest

            def test_container_basics(docker_helper):
                container = docker_helper.create_container('test', '{}')
                docker_helper.start_container(container)

                assert container.status == 'running'

                docker_helper.stop_and_remove_container(container)

                with pytest.raises(NotFound):
                    container.reload()
        """.format(IMG))

        result = testdir.runpytest()
        result.assert_outcomes(passed=1)

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
        container = helper.create_container('test', IMG)

        # Test things are torn down
        with pytest.raises(StopIteration):
            next(fixture_gen)

        with pytest.raises(docker.errors.NotFound):
            container.reload()


@dockertest()
class TestImagePullFixtureFunc:
    def test_fixture(self, testdir):
        """
        When the fixture is used in a test, the image passed to the test
        should have the right tag.
        """
        testdir.makeconftest("""
            from seaworthy.pytest.fixtures import image_pull_fixture

            fixture = image_pull_fixture('busybox', name='image')
        """.format(IMG))

        testdir.makepyfile("""
            def test_image_pull(image):
                assert 'busybox:latest' in image.tags
        """)

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
    def test_fixture(self, testdir):
        """
        When the fixture is used in a test, the container passed to the test
        function should be running.
        """
        testdir.makeconftest("""
            from seaworthy.containers.base import ContainerBase
            from seaworthy.pytest.fixtures import container_fixture

            fixture = container_fixture(ContainerBase(name='test', image='{}'),
                                        'container')
        """.format(IMG))

        testdir.makepyfile("""
            def test_create_container(container):
                assert container.inner().status == 'running'
        """)

        result = testdir.runpytest()
        result.assert_outcomes(passed=1)

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
    def test_fixture(self, testdir):
        """
        When the fixture is used in a test, it should be cleaned when the test
        function is marked to be cleaned. The container passed to the test
        function should be running.
        """
        testdir.makeconftest("""
            from seaworthy.containers.base import ContainerBase
            from seaworthy.pytest.fixtures import clean_container_fixtures


            class CleanableContainer(ContainerBase):
                def __init__(self):
                    super().__init__(name='test', image='{}')
                    self.cleaned = False

                def clean(self):
                    self.cleaned = True

                def was_cleaned(self):
                    cleaned = self.cleaned
                    self.cleaned = False
                    return cleaned


            f1, f2 = clean_container_fixtures(
                CleanableContainer(), 'cleanable')
        """.format(IMG))

        testdir.makepyfile("""
            import pytest


            def test_dirty(cleanable):
                assert not cleanable.was_cleaned()
                assert cleanable.inner().status == 'running'

            @pytest.mark.clean_cleanable
            def test_clean(cleanable):
                assert cleanable.was_cleaned()
                assert cleanable.inner().status == 'running'
        """)

        result = testdir.runpytest()
        result.assert_outcomes(passed=2)

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
