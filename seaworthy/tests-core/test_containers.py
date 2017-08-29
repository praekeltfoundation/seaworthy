import unittest

from docker.models.containers import Container

from seaworthy.checks import dockertest
from seaworthy.containers import ContainerBase
from seaworthy.dockerhelper import DockerHelper

IMG = 'nginx:alpine'
docker_helper = DockerHelper()


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    docker_helper.setup()
    docker_helper.pull_image_if_not_found(IMG)


@dockertest()
def tearDownModule():  # noqa: N802
    docker_helper.teardown()


@dockertest()
class TestContainerBase(unittest.TestCase):
    def setUp(self):
        self.base = ContainerBase('test', IMG)

    def test_create_only_if_not_created(self):
        """The container cannot be created more than once."""
        self.base.create_and_start(docker_helper, pull=False)

        # We can't create the container when it's already created
        with self.assertRaises(RuntimeError) as cm:
            self.base.create_and_start(docker_helper, pull=False)
        self.assertEqual(str(cm.exception), 'Container already created.')

        self.base.stop_and_remove(docker_helper)

    def test_remove_only_if_created(self):
        """The container can only be removed if it has been created."""
        self.base.create_and_start(docker_helper, pull=False)

        # We can remove the container if it's created
        self.base.stop_and_remove(docker_helper)

        with self.assertRaises(RuntimeError) as cm:
            self.base.stop_and_remove(docker_helper)
        self.assertEqual(str(cm.exception), 'Container not created yet.')

    def test_container_only_if_created(self):
        """
        We can only access the inner Container object if the container has been
        created.
        """
        # If we try get the container before it's created it'll fail
        with self.assertRaises(RuntimeError) as cm:
            self.base.inner()
        self.assertEqual(str(cm.exception), 'Container not created yet.')

        self.base.create_and_start(docker_helper, pull=False)

        # We can get the container once it's created
        container = self.base.inner()
        self.assertIsInstance(container, Container)

        self.base.stop_and_remove(docker_helper)
        with self.assertRaises(RuntimeError) as cm:
            self.base.inner()
        self.assertEqual(str(cm.exception), 'Container not created yet.')

    def test_default_create_kwargs(self):
        """
        The default return value of the ``create_kwargs`` method is an empty
        dict.
        """
        self.assertEqual(self.base.create_kwargs(), {})

    def test_default_clean(self):
        """By default, the ``clean`` method raises a NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.base.clean()
