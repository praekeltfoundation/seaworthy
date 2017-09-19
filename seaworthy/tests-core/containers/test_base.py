import unittest

from docker.models.containers import Container

from seaworthy.checks import docker_client, dockertest
from seaworthy.containers.base import ContainerBase
from seaworthy.dockerhelper import DockerHelper, fetch_images

IMG = 'nginx:alpine'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    with docker_client() as client:
        fetch_images(client, [IMG])


@dockertest()
class TestContainerBase(unittest.TestCase):
    def setUp(self):
        self.base = ContainerBase('test', IMG)

    def make_helper(self, setup=True):
        """
        Create and return a DockerHelper instance that will be cleaned up after
        the test.
        """
        dh = DockerHelper()
        self.addCleanup(dh.teardown)
        dh.setup()
        return dh

    def test_create_only_if_not_created(self):
        """The container cannot be created more than once."""
        dh = self.make_helper()
        self.base.create_and_start(dh, pull=False)

        # We can't create the container when it's already created
        with self.assertRaises(RuntimeError) as cm:
            self.base.create_and_start(dh, pull=False)
        self.assertEqual(str(cm.exception), 'Container already created.')

        self.base.stop_and_remove(dh)

    def test_remove_only_if_created(self):
        """The container can only be removed if it has been created."""
        dh = self.make_helper()
        self.base.create_and_start(dh, pull=False)

        # We can remove the container if it's created
        self.base.stop_and_remove(dh)

        with self.assertRaises(RuntimeError) as cm:
            self.base.stop_and_remove(dh)
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

        dh = self.make_helper()
        self.base.create_and_start(dh, pull=False)

        # We can get the container once it's created
        container = self.base.inner()
        self.assertIsInstance(container, Container)

        self.base.stop_and_remove(dh)
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

    def test_get_host_port(self):
        """
        We can get the host port mapping of a container.
        """
        self.base.create_kwargs = lambda: {'ports': {
            '8080/tcp': ('127.0.0.1',),
            '9090/tcp': ('127.0.0.1', '10701'),
        }}
        dh = self.make_helper()
        self.base.create_and_start(dh, pull=False)

        # We get a random high port number here.
        random_host_port = self.base.get_host_port('8080/tcp')
        self.assertGreater(int(random_host_port), 1024)
        self.assertLess(int(random_host_port), 65536)

        # We get the specific port we defined here.
        self.assertEqual(self.base.get_host_port('9090/tcp', 0), '10701')
