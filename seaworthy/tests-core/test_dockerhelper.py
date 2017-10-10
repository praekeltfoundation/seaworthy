import unittest

import docker

from seaworthy.checks import docker_client, dockertest
from seaworthy.dockerhelper import DockerHelper, fetch_images


# We use this image to test with because it is a small (~7MB) image from
# https://github.com/docker-library/official-images that runs indefinitely with
# no configuration.
IMG = 'nginx:alpine'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    with docker_client() as client:
        fetch_images(client, [IMG])


def filter_by_name(things, prefix):
    return [t for t in things if t.name.startswith(prefix)]


@dockertest()
class TestDockerHelper(unittest.TestCase):
    def setUp(self):
        self.client = docker.client.from_env()
        self.addCleanup(self.client.api.close)

    def make_helper(self, *args, setup=True, **kwargs):
        """
        Create and return a DockerHelper instance that will be cleaned up after
        the test.
        """
        dh = DockerHelper(*args, **kwargs)
        self.addCleanup(dh.teardown)
        if setup:
            dh.setup()
        return dh

    def list_networks(self, *args, namespace='test', **kw):
        return filter_by_name(
            self.client.networks.list(*args, **kw), '{}_'.format(namespace))

    def list_containers(self, *args, namespace='test', **kw):
        return filter_by_name(
            self.client.containers.list(*args, **kw), '{}_'.format(namespace))

    def test_lifecycle_network(self):
        """
        The default network can only be created once and is removed during
        teardown.
        """
        dh = self.make_helper()
        # The default network isn't created unless required
        network = dh.get_default_network(create=False)
        self.assertIsNone(network)

        # Create the default network
        network = dh.get_default_network(create=True)
        self.assertIsNotNone(network)

        # We can try to get the network lots of times and we get the same one
        # and new ones aren't created.
        dh.get_default_network(create=False)
        dh.get_default_network(create=True)
        networks = self.list_networks()
        self.assertEqual(networks, [network])

        # The default network is removed on teardown
        dh.teardown()
        network = dh.get_default_network(create=False)
        self.assertIsNone(network)

    def test_network_already_exists(self):
        """
        If the default network already exists when we try to create it, we
        fail.
        """
        # We use a separate DockerHelper (with the usual cleanup) to create the
        # test network so that the DockerHelper under test will see that it
        # already exists.
        dh1 = self.make_helper()
        dh1.get_default_network()
        # Now for the test.
        dh2 = self.make_helper()
        with self.assertRaises(RuntimeError) as cm:
            dh2.get_default_network()
        self.assertIn('network', str(cm.exception))
        self.assertIn('already exists', str(cm.exception))

    def test_teardown_safe(self):
        """
        DockerHelper.teardown() is safe to call multiple times, both before and
        after setup.

        There are no assertions here. We only care that calling teardown never
        raises any exceptions.
        """
        dh = self.make_helper(setup=False)
        # These should silently do nothing.
        dh.teardown()
        dh.teardown()
        # Run setup so we have something to tear down.
        dh.setup()
        # This should do the teardown.
        dh.teardown()
        # This should silently do nothing.
        dh.teardown()

    def test_teardown_containers(self):
        """
        DockerHelper.teardown() will remove any containers that were created,
        no matter what state they are in or even whether they still exist.
        """
        dh = self.make_helper()
        self.assertEqual([], self.list_containers(all=True))
        con_created = dh.create_container('created', IMG)
        self.assertEqual(con_created.status, 'created')

        con_running = dh.create_container('running', IMG)
        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')

        con_stopped = dh.create_container('stopped', IMG)
        dh.start_container(con_stopped)
        self.assertEqual(con_stopped.status, 'running')
        dh.stop_container(con_stopped)
        self.assertNotEqual(con_stopped.status, 'running')

        con_removed = dh.create_container('removed', IMG)
        # We remove this behind the helper's back so the helper thinks it still
        # exists at teardown time.
        con_removed.remove()
        with self.assertRaises(docker.errors.NotFound):
            con_removed.reload()

        self.assertEqual(
            set([con_created, con_running, con_stopped]),
            set(self.list_containers(all=True)))

        with self.assertLogs('seaworthy', level='WARNING') as cm:
            dh.teardown()
        self.assertEqual(sorted(l.getMessage() for l in cm.records), [
            "Container 'test_created' still existed during teardown",
            "Container 'test_running' still existed during teardown",
            "Container 'test_stopped' still existed during teardown",
        ])
        self.assertEqual([], self.list_containers(all=True))

    def test_create_container(self):
        """
        We can create a container with various parameters without starting it.
        """
        dh = self.make_helper()

        con_simple = dh.create_container('simple', IMG)
        self.addCleanup(dh.remove_container, con_simple)
        self.assertEqual(con_simple.status, 'created')
        self.assertEqual(con_simple.attrs['Path'], 'nginx')

        con_cmd = dh.create_container('cmd', IMG, command='echo hello')
        self.addCleanup(dh.remove_container, con_cmd)
        self.assertEqual(con_cmd.status, 'created')
        self.assertEqual(con_cmd.attrs['Path'], 'echo')

        con_env = dh.create_container('env', IMG, environment={'FOO': 'bar'})
        self.addCleanup(dh.remove_container, con_env)
        self.assertEqual(con_env.status, 'created')
        self.assertIn('FOO=bar', con_env.attrs['Config']['Env'])

    def test_container_networks(self):
        """
        When a container is created, the network settings are respected, and if
        no network settings are specified, the container is connected to a
        default network.
        """
        dh = self.make_helper()

        # TODO: Custom network

        # When 'network_mode' is provided, the default network is not used
        con_mode = dh.create_container('mode', IMG, network_mode='none')
        self.addCleanup(dh.remove_container, con_mode)
        networks = con_mode.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), ['none'])

        # When 'network_disabled' is True, the default network is not used
        con_disabled = dh.create_container(
            'disabled', IMG, network_disabled=True)
        self.addCleanup(dh.remove_container, con_disabled)
        self.assertEqual(con_disabled.attrs['NetworkSettings']['Networks'], {})

        con_default = dh.create_container('default', IMG)
        self.addCleanup(dh.remove_container, con_default)
        networks = con_default.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), ['test_default'])
        network = networks['test_default']
        self.assertCountEqual(
            network['Aliases'], [con_default.id[:12], 'default'])

    def test_start_container(self):
        """
        We can start a container after creating it.
        """
        dh = self.make_helper()

        con = dh.create_container('con', IMG)
        self.addCleanup(dh.remove_container, con)
        self.assertEqual(con.status, 'created')
        dh.start_container(con)
        self.assertEqual(con.status, 'running')

    def test_stop_container(self):
        """
        We can stop a running container.
        """
        # We don't test the timeout because that's just passed directly through
        # to docker and it's nontrivial to construct a container that takes a
        # specific amount of time to stop.
        dh = self.make_helper()

        con = dh.create_container('con', IMG)
        self.addCleanup(dh.remove_container, con)
        dh.start_container(con)
        self.assertEqual(con.status, 'running')
        dh.stop_container(con)
        self.assertEqual(con.status, 'exited')

    def test_remove_container(self):
        """
        We can remove a not-running container.
        """
        dh = self.make_helper()

        con_created = dh.create_container('created', IMG)
        self.assertEqual(con_created.status, 'created')
        dh.remove_container(con_created)
        with self.assertRaises(docker.errors.NotFound):
            con_created.reload()

        con_stopped = dh.create_container('stopped', IMG)
        dh.start_container(con_stopped)
        dh.stop_container(con_stopped)
        self.assertEqual(con_stopped.status, 'exited')
        dh.remove_container(con_stopped)
        with self.assertRaises(docker.errors.NotFound):
            con_stopped.reload()

    def test_remove_container_force(self):
        """
        We can't remove a running container without forcing it.
        """
        dh = self.make_helper()

        con_running = dh.create_container('running', IMG)
        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')
        with self.assertRaises(docker.errors.APIError):
            dh.remove_container(con_running, force=False)
        dh.remove_container(con_running)
        with self.assertRaises(docker.errors.NotFound):
            con_running.reload()

    def test_stop_and_remove_container(self):
        """
        This does the stop and remove as separate steps, so we can remove a
        running container without forcing.
        """
        dh = self.make_helper()

        con_running = dh.create_container('running', IMG)
        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')
        dh.stop_and_remove_container(con_running, remove_force=False)
        with self.assertRaises(docker.errors.NotFound):
            con_running.reload()

    def test_pull_image_if_not_found(self):
        """
        We check if the image is already present and pull it if necessary.
        """
        dh = self.make_helper()

        # First, remove the image if it's already present. (We use the busybox
        # image for this test because it's the smallest I can find that is
        # likely to be reliably available.)
        try:
            self.client.images.get('busybox:latest')
        except docker.errors.ImageNotFound:  # pragma: no cover
            pass
        else:
            self.client.images.remove('busybox:latest')  # pragma: no cover

        # Pull the image, which we now know we don't have.
        with self.assertLogs('seaworthy', level='INFO') as cm:
            dh.pull_image_if_not_found('busybox:latest')
        self.assertEqual(
            [l.getMessage() for l in cm.records],
            ["Pulling tag 'busybox:latest'..."])

        # Pull the image again, now that we know it's present.
        with self.assertLogs('seaworthy', level='DEBUG') as cm:
            dh.pull_image_if_not_found('busybox:latest')
        logs = [l.getMessage() for l in cm.records]
        self.assertEqual(len(logs), 1)
        self.assertRegex(
            logs[0],
            r"Found image 'sha256:[a-f0-9]{64}' for tag 'busybox:latest'")

    def test_namespace(self):
        """
        When the helper has its default namespace, the default network and all
        created containers should have names prefixed with the namespace.
        """
        dh = self.make_helper()

        network = dh.get_default_network()
        self.assertEqual(network.name, 'test_default')

        con = dh.create_container('con', IMG)
        self.addCleanup(dh.remove_container, con)
        self.assertEqual(con.name, 'test_con')

    def test_custom_namespace(self):
        """
        When the helper has a custom namespace, the default network and all
        created containers should have names prefixed with the namespace.
        """
        dh = self.make_helper(namespace='integ')

        network = dh.get_default_network()
        self.assertEqual(network.name, 'integ_default')

        con = dh.create_container('con', IMG)
        self.addCleanup(dh.remove_container, con)
        self.assertEqual(con.name, 'integ_con')
