import time
import unittest
from datetime import datetime

from docker.models.containers import Container

from seaworthy.checks import docker_client, dockertest
from seaworthy.containers.base import ContainerBase
from seaworthy.dockerhelper import DockerHelper, fetch_images

IMG_SCRIPT = 'alpine:latest'
IMG_WAIT = 'nginx:alpine'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    with docker_client() as client:
        fetch_images(client, [IMG_SCRIPT, IMG_WAIT])


@dockertest()
class TestContainerBase(unittest.TestCase):
    def setUp(self):
        self.dh = DockerHelper()
        self.addCleanup(self.dh.teardown)
        self.dh.setup()

        self.base = ContainerBase('wait', IMG_WAIT)
        self.addCleanup(self._cleanup_container, self.base)

    def _cleanup_container(self, container):
        if container._container is not None:
            container.stop_and_remove(self.dh)

    def test_create_only_if_not_created(self):
        """The container cannot be created more than once."""
        self.base.create_and_start(self.dh, pull=False)

        # We can't create the container when it's already created
        with self.assertRaises(RuntimeError) as cm:
            self.base.create_and_start(self.dh, pull=False)
        self.assertEqual(str(cm.exception), 'Container already created.')

        self.base.stop_and_remove(self.dh)

    def test_remove_only_if_created(self):
        """The container can only be removed if it has been created."""
        self.base.create_and_start(self.dh, pull=False)

        # We can remove the container if it's created
        self.base.stop_and_remove(self.dh)

        with self.assertRaises(RuntimeError) as cm:
            self.base.stop_and_remove(self.dh)
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

        self.base.create_and_start(self.dh, pull=False)

        # We can get the container once it's created
        container = self.base.inner()
        self.assertIsInstance(container, Container)

        self.base.stop_and_remove(self.dh)
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
        self.base.create_and_start(self.dh, pull=False)

        # We get a random high port number here.
        random_host_port = self.base.get_host_port('8080/tcp')
        self.assertGreater(int(random_host_port), 1024)
        self.assertLess(int(random_host_port), 65536)

        # We get the specific port we defined here.
        self.assertEqual(self.base.get_host_port('9090/tcp', 0), '10701')

    def run_logs_container(self, logs, wait=True, delay=0.01):
        # Sleep a millisecond between lines to ensure ordering across stdout
        # and stderr.
        script = '\nsleep {}\n'.format(delay).join(logs)

        script_con = ContainerBase('script', IMG_SCRIPT)
        self.addCleanup(self._cleanup_container, script_con)

        script_con.create_kwargs = lambda: {'command': ['sh', '-c', script]}
        script_con.create_and_start(self.dh, pull=False)
        # Wait for the output to arrive.
        if wait:
            time.sleep(len(logs) * delay)
        return script_con

    def test_get_logs_out_err(self):
        """
        We can choose stdout and/or stderr when getting logs from a container.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ])

        self.assertEqual(script.get_logs(), b'o0\ne0\no1\ne1\n')
        self.assertEqual(script.get_logs(stdout=False), b'e0\ne1\n')
        self.assertEqual(script.get_logs(stderr=False), b'o0\no1\n')

    def test_get_logs_tail(self):
        """
        We can choose how many lines to tail when getting logs from a
        container.

        NOTE: Lines are tailed *before* stdout/stderr are filtered out.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ])

        self.assertEqual(script.get_logs(tail='all'), b'o0\ne0\no1\ne1\n')
        self.assertEqual(script.get_logs(tail=10000), b'o0\ne0\no1\ne1\n')
        self.assertEqual(script.get_logs(tail=0), b'')
        self.assertEqual(script.get_logs(tail=1), b'e1\n')
        self.assertEqual(script.get_logs(tail=2), b'o1\ne1\n')
        # The entries are tailed *before* they're filtered. :-(
        self.assertEqual(script.get_logs(stderr=False, tail=1), b'')
        self.assertEqual(script.get_logs(stderr=False, tail=2), b'o1\n')
        self.assertEqual(script.get_logs(stderr=False, tail=3), b'o1\n')
        self.assertEqual(script.get_logs(stderr=False, tail=4), b'o0\no1\n')

    def test_get_logs_timestamps(self):
        """
        We can ask for timestamps on our logs.
        """
        before = datetime.utcnow()
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ])
        after = datetime.utcnow()

        self.assertEqual(script.get_logs(), b'o0\ne0\no1\ne1\n')
        raw_lines = script.get_logs(timestamps=True).splitlines()

        earlier = before
        for line, expected in zip(raw_lines, [b'o0', b'e0', b'o1', b'e1']):
            ts, l = line.split(b' ', 1)
            self.assertEqual(l, expected)
            # Truncate the nanoseconds, because we can't parse them.
            ts = (ts[:26] + ts[-1:]).decode('utf8')
            ts = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%fZ')
            self.assertLess(earlier, ts)
            earlier = ts
        self.assertLess(earlier, after)

    def test_stream_logs_timeout(self):
        """
        We can stream logs with a timeout.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ], delay=0.2, wait=False)

        time.sleep(0.01)
        lines = []
        with self.assertRaises(TimeoutError):
            for line in script.stream_logs(timeout=0.3):
                lines.append(line)
        # We missed the first line and time out before the third.
        self.assertEqual(lines, [b'e0\n'])

        lines = []
        for line in script.stream_logs(timeout=1.0):
            lines.append(line)
        # We should get the third and fourth now.
        self.assertEqual(lines, [b'o1\n', b'e1\n'])

    def test_stream_old_logs(self):
        """
        We can stream logs, including old logs, with a timeout.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ], delay=0.2, wait=False)

        time.sleep(0.01)
        lines = []
        with self.assertRaises(TimeoutError):
            for line in script.stream_logs(old_logs=True, timeout=0.3):
                lines.append(line)
        # We get the (old) first line and time out before the third.
        self.assertEqual(lines, [b'o0\n', b'e0\n'])

        lines = []
        for line in script.stream_logs(old_logs=True, timeout=1.0):
            lines.append(line)
        self.assertEqual(lines, [b'o0\n', b'e0\n', b'o1\n', b'e1\n'])

    def test_stream_logs_stdout(self):
        """
        We can choose stdout when streaming logs.
        """
        script = self.run_logs_container([
            'echo "first"',
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ], delay=0.1, wait=False)
        time.sleep(0.01)

        lines = []
        for line in script.stream_logs(stderr=False, timeout=1.0):
            lines.append(line)
        self.assertEqual(lines, [b'o0\n', b'o1\n'])

    def test_stream_logs_stderr(self):
        """
        We can choose stderr when streaming logs.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ], delay=0.1, wait=False)
        time.sleep(0.01)

        lines = []
        for line in script.stream_logs(stdout=False, timeout=1.0):
            lines.append(line)
        self.assertEqual(lines, [b'e0\n', b'e1\n'])
