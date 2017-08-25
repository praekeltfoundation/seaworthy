import unittest

import docker

from seaworthy.checks import dockertest, fetch_images
from seaworthy.dockerhelper import DockerHelper


# We use this image to test with because it is a small (~7MB) image from
# https://github.com/docker-library/official-images that runs indefinitely with
# no configuration.
TEST_IMAGE = 'nginx:alpine'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    fetch_images([TEST_IMAGE])


def filter_by_name(things, prefix):
    return [t for t in things if t.name.startswith(prefix)]


@dockertest()
class TestDockerHelper(unittest.TestCase):
    def setUp(self):
        self.client = docker.client.from_env()
        self.addCleanup(self.client.api.close)

    def make_helper(self):
        """
        Create and return a DockerHelper instance that will be cleaned up after
        the test.
        """
        dh = DockerHelper()
        self.addCleanup(dh.teardown)
        return dh

    def list_networks(self, *args, **kw):
        return filter_by_name(
            self.client.networks.list(*args, **kw), 'test_')

    def list_containers(self, *args, **kw):
        return filter_by_name(
            self.client.containers.list(*args, **kw), 'test_')

    def test_lifecycle_network(self):
        """
        A DockerHelper creates a test network during setup and removes that
        network during teardown.
        """
        dh = self.make_helper()
        self.assertEqual([], self.list_networks())
        dh.setup()
        self.assertNotEqual([], self.list_networks())
        dh.teardown()
        self.assertEqual([], self.list_networks())

    def test_network_already_exists(self):
        """
        If the test network already exists during setup, we fail.
        """
        # We use a separate DockerHelper (with the usual cleanup) to create the
        # test network so that the DockerHelper under test will see that it
        # already exists.
        dh_outer = self.make_helper()
        dh_outer.setup()
        # Now for the test.
        dh = self.make_helper()
        with self.assertRaises(RuntimeError) as cm:
            dh.setup()
        self.assertIn('network', str(cm.exception))
        self.assertIn('already exists', str(cm.exception))

    def test_teardown_safe(self):
        """
        DockerHelper.teardown() is safe to call multiple times, both before and
        after setup.

        There are no assertions here. We only care that calling teardown never
        raises any exceptions.
        """
        dh = self.make_helper()
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
        dh.setup()
        self.assertEqual([], self.list_containers(all=True))
        con_created = dh.create_container('created', TEST_IMAGE)
        self.assertEqual(con_created.status, 'created')

        con_running = dh.create_container('running', TEST_IMAGE)
        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')

        con_stopped = dh.create_container('stopped', TEST_IMAGE)
        dh.start_container(con_stopped)
        self.assertEqual(con_stopped.status, 'running')
        dh.stop_container(con_stopped)
        self.assertNotEqual(con_stopped.status, 'running')

        con_removed = dh.create_container('removed', TEST_IMAGE)
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
        self.assertEquals(sorted(l.getMessage() for l in cm.records), [
            "Container 'test_created' still existed during teardown",
            "Container 'test_running' still existed during teardown",
            "Container 'test_stopped' still existed during teardown",
        ])
        self.assertEqual([], self.list_containers(all=True))
