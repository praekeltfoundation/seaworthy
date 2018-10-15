import unittest

from seaworthy.checks import docker_client, dockertest
from seaworthy.containers.redis import RedisContainer
from seaworthy.events import wait_for_healthcheck
from seaworthy.helpers import DockerHelper, fetch_images


# TODO: Find an image to test with that is actually maintained
IMG_HEALTHCHECK = 'healthcheck/redis:alpine'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    with docker_client() as client:
        fetch_images(client, [IMG_HEALTHCHECK])


class TestWaitForHealthcheckFunc(unittest.TestCase):
    def setUp(self):
        self.dh = DockerHelper()
        self.addCleanup(self.dh.teardown)

        self.definition = RedisContainer(image=IMG_HEALTHCHECK, helper=self.dh)
        self.definition.run()
        self.addCleanup(self.definition.teardown)

    def test_healthcheck_pass(self):
        """
        A healthy container should pass the health check eventually.

        TODO: Make this not take ages and ages by reducing the interval (the
        image seems to default to 30s) between health checks.
        """
        wait_for_healthcheck(self.definition.inner(), timeout=45)
