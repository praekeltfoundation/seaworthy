import unittest

import docker

from seaworthy.checks import dockertest
from seaworthy.dockerhelper import DockerHelper
from seaworthy.utils import resource_name


@dockertest()
class TestDockerHelper(unittest.TestCase):
    def make_client(self):
        """
        Create and return a docker client that will be cleaned up properly.
        """
        client = docker.client.from_env()
        self.addCleanup(client.api.close)
        return client

    def make_helper(self):
        """
        Create and return a DockerHelper instance that will be cleaned up after
        the test.
        """
        dh = DockerHelper()
        self.addCleanup(dh.teardown)
        return dh

    def test_lifecycle_network(self):
        """
        A DockerHelper creates a test network during setup and removes that
        network during teardown.
        """
        client = self.make_client()
        network_name = resource_name('default')
        dh = self.make_helper()
        self.assertEqual([], client.networks.list(names=[network_name]))
        dh.setup()
        self.assertNotEqual([], client.networks.list(names=[network_name]))
        dh.teardown()
        self.assertEqual([], client.networks.list(names=[network_name]))

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
