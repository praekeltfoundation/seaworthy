import unittest
from datetime import datetime

from seaworthy.checks import docker_client, dockertest
from seaworthy.helpers import DockerHelper, fetch_images
from seaworthy.stream.logs import stream_logs, wait_for_logs_matching
from seaworthy.stream.matchers import EqualsMatcher

from .fake_stream import FakeStreamSource

# We use this image to test with because it is a small (~4MB) image from
# https://github.com/docker-library/official-images that we can run shell
# scripts in.
IMG = 'alpine:latest'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    with docker_client() as client:
        fetch_images(client, [IMG])


class FakeLogsContainer(FakeStreamSource):
    """
    A container object stub that emits canned logs.

    Logs can either be streamed through a socket using ``.attach_socket()`` or
    tailed by using ``.logs()``. After a log entry has been streamed, it is
    stored and we don't stream it next time. Only logs that have already been
    streamed are tailed.
    """

    def logs(self, stream=False, **kw):
        tail = kw.pop('tail', 'all')
        if stream:
            return self.stream_items(tail, kw)
        else:
            return b''.join(self.tail_items(tail))


class TestFakeLogsContainer(unittest.TestCase):
    def mkcontainer(self, *args, **kw):
        kw.setdefault('close_timeout', 0.1)
        con = FakeLogsContainer(*args, **kw)
        self.addCleanup(con.cleanup)
        return con

    def stream(self, con, **kw):
        return list(stream_logs(con, **kw))

    def test_empty(self):
        """
        Streaming logs for a container with no logs returns immediately.
        """
        con = self.mkcontainer([])
        self.assertEqual(self.stream(con), [])
        self.assertEqual(con.logs(tail=1), b'')

    def test_tail_only_returns_streamed(self):
        """
        Only logs that have been streamed can be tailed.
        """
        con = self.mkcontainer([(0, b'hello\n'), (0, b'goodbye\n')])
        self.assertEqual(con.logs(tail=2), b'')
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        self.assertEqual(con.logs(tail=2), b'hello\ngoodbye\n')

    def test_tail_tails(self):
        """
        Tailing returns the last N log lines, or all line if there are fewer
        than N or if N is 'all' (which is the default).
        """
        con = self.mkcontainer([(0, b'hello\n'), (0, b'goodbye\n')])
        self.stream(con)
        self.assertEqual(con.logs(tail=1), b'goodbye\n')
        self.assertEqual(con.logs(tail=2), b'hello\ngoodbye\n')
        self.assertEqual(con.logs(tail=3), b'hello\ngoodbye\n')
        self.assertEqual(con.logs(tail='all'), b'hello\ngoodbye\n')
        self.assertEqual(con.logs(), b'hello\ngoodbye\n')

    def test_streaming_waits(self):
        """
        Streamed logs will be returned at specified intervals. Any logs that
        have already been streamed are not returned again if we set tail=0.

        NOTE: This test measures wall-clock time, so if something causes it to
              be too slow the second assertion may fail.
        """
        con = self.mkcontainer([(0.1, b'hello\n'), (0.2, b'goodbye\n')])
        t0 = datetime.now()
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        t1 = datetime.now()
        self.assertEqual(self.stream(con, tail=0), [])
        t2 = datetime.now()
        self.assertLess(0.3, (t1 - t0).total_seconds())
        self.assertLess((t2 - t1).total_seconds(), 0.3)


class TestStreamLogsFunc(unittest.TestCase):
    def mkcontainer(self, *args, **kw):
        kw.setdefault('close_timeout', 0.1)
        con = FakeLogsContainer(*args, **kw)
        self.addCleanup(con.cleanup)
        return con

    def stream_only(self, con, timeout=1):
        return list(stream_logs(con, tail=0, timeout=timeout))

    def stream_logs(self, con, timeout=0.5, **kw):
        return stream_logs(con, timeout=timeout, **kw)

    def test_stream_only(self):
        """
        If there are no historical logs, we get all the streamed logs.
        """
        con = self.mkcontainer([
            (0.1, b'hello\n'),
            (0.1, b'goodbye\n'),
        ])
        self.assertEqual(
            list(self.stream_logs(con, tail=0)), [b'hello\n', b'goodbye\n'])

    def test_historical_only(self):
        """
        If all the logs have been streamed, we only get the old ones.
        """
        con = self.mkcontainer([
            (0.1, b'hello\n'),
            (0.1, b'goodbye\n'),
        ])
        self.assertEqual(self.stream_only(con), [b'hello\n', b'goodbye\n'])
        self.assertEqual(self.stream_only(con), [])
        self.assertEqual(
            list(self.stream_logs(con)), [b'hello\n', b'goodbye\n'])

    def test_timeout_and_stream_again(self):
        """
        If we take too long to get the next line, we time out. When we stream
        again, we get historical logs as well as new ones.
        """
        con = self.mkcontainer([
            (0.1, b'hello\n'),
            (0.2, b'goodbye\n'),
        ])
        lines = []
        with self.assertRaises(TimeoutError):
            for line in self.stream_logs(con, timeout=0.15):
                lines.append(line)
        self.assertEqual(lines, [b'hello\n'])
        lines = list(self.stream_logs(con, timeout=0.35))
        self.assertEqual(lines, [b'hello\n', b'goodbye\n'])


class TestWaitForLogsMatchingFunc(unittest.TestCase):
    def mkcontainer(self, *args, **kw):
        kw.setdefault('close_timeout', 0.1)
        con = FakeLogsContainer(*args, **kw)
        self.addCleanup(con.cleanup)
        return con

    def wflm(self, con, matcher, timeout=0.5, **kw):
        return wait_for_logs_matching(con, matcher, timeout=timeout, **kw)

    def test_one_matching_line(self):
        """
        If one matching line is logged, all is happy.
        """
        con = self.mkcontainer([
            (0, b'hello\n'),
        ])
        # If this doesn't raise an exception, the test passes.
        self.wflm(con, EqualsMatcher('hello'))

    def test_one_non_matching_line(self):
        """
        If there's no match by the time the logs end, we raise an exception.
        """
        con = self.mkcontainer([
            (0, b'goodbye\n'),
        ])
        with self.assertRaises(RuntimeError) as cm:
            self.wflm(con, EqualsMatcher('hello'))
        self.assertIn(
            "Logs matching EqualsMatcher('hello') not found.",
            str(cm.exception))
        self.assertIn('goodbye\n', str(cm.exception))

    def test_timeout_first_line(self):
        """
        If we take too long to get the first line, we time out.
        """
        con = self.mkcontainer([
            (0.2, b'hello\n'),
        ])
        with self.assertRaises(TimeoutError) as cm:
            self.wflm(con, EqualsMatcher('hello'), timeout=0.1)
        self.assertIn(
            "Timeout (0.1s) waiting for logs matching EqualsMatcher('hello').",
            str(cm.exception))
        self.assertNotIn('hello\n', str(cm.exception))

    def test_timeout_later_line(self):
        """
        If we take too long to get a later line, we time out.
        """
        con = self.mkcontainer([
            (0, b'hi\n'),
            (0.2, b'hello\n'),
        ])
        with self.assertRaises(TimeoutError) as cm:
            self.wflm(con, EqualsMatcher('hello'), timeout=0.1)
        self.assertIn(
            "Timeout (0.1s) waiting for logs matching EqualsMatcher('hello').",
            str(cm.exception))
        self.assertIn('hi\n', str(cm.exception))
        self.assertNotIn('hello\n', str(cm.exception))

    def test_default_encoding(self):
        """
        By default, we assume logs are UTF-8.
        """
        con = self.mkcontainer([
            (0, b'\xc3\xbeorn\n'),
        ])
        # If this doesn't raise an exception, the test passes.
        self.wflm(con, EqualsMatcher('\u00feorn'))

    def test_encoding(self):
        """
        We can operate on logs that use excitingly horrible encodings.
        """
        con = self.mkcontainer([
            (0, b'\xfeorn\n'),
        ])
        # If this doesn't raise an exception, the test passes.
        self.wflm(con, EqualsMatcher('\u00feorn'), encoding='latin1')

    def test_kwargs(self):
        """
        We pass through any kwargs we don't recognise to docker.
        """
        con = self.mkcontainer([(0, b'hi\n')], {'stdout': False})
        with self.assertRaises(AssertionError):
            self.wflm(con, EqualsMatcher('hi'))
        with self.assertRaises(AssertionError):
            self.wflm(con, EqualsMatcher('hi'), stdout=False, stderr=False)
        self.wflm(con, EqualsMatcher('hi'), stdout=False)


class FakeAndRealContainerMixin:
    def wflm(self, con, matcher, timeout=0.5, **kw):
        return wait_for_logs_matching(con, matcher, timeout=timeout, **kw)

    def stream_logs(self, con, timeout=0.5, **kw):
        for line in stream_logs(con, timeout=timeout, **kw):
            yield line

    def test_fake_and_real_logging_behaviour(self):
        """
        Our fake logs container should exhibit similar behaviour to a real
        container.
        """
        logger = self.start_logging_container()
        self.wflm(logger, EqualsMatcher('Log entry 1'), timeout=1)

        early_logs = logger.logs().decode('utf8').splitlines()
        self.assertIn('Log entry 1', early_logs)
        self.assertNotIn('Log entry 4', early_logs)

        streamed_logs = []
        with self.assertRaises(TimeoutError):
            for line in self.stream_logs(logger, tail=0, timeout=0.7):
                streamed_logs.append(line.decode('utf8').rstrip())
        self.assertNotIn('Log entry 1', streamed_logs)
        self.assertIn('Log entry 4', streamed_logs)
        self.assertNotIn('Log entry 9', streamed_logs)

        streamed_logs = []
        for line in self.stream_logs(logger, timeout=2):
            streamed_logs.append(line.decode('utf8').rstrip())
        self.assertIn('Log entry 1', streamed_logs)
        self.assertIn('Log entry 4', streamed_logs)
        self.assertIn('Log entry 9', streamed_logs)


class TestWithFakeContainer(unittest.TestCase, FakeAndRealContainerMixin):
    def mkcontainer(self, *args, **kw):
        kw.setdefault('close_timeout', 0.1)
        con = FakeLogsContainer(*args, **kw)
        self.addCleanup(con.cleanup)
        return con

    def start_logging_container(self):
        return self.mkcontainer([
            (0.2, 'Log entry {}\n'.format(n).encode('utf8'))
            for n in range(10)])


@dockertest()
class TestWithRealContainer(unittest.TestCase, FakeAndRealContainerMixin):
    def setUp(self):
        self.dh = DockerHelper()
        self.addCleanup(self.dh.teardown)

    def start_logging_container(self):
        script = '\n'.join([
            'for n in 0 1 2 3 4 5 6 7 8 9; do',
            '    sleep 0.2',
            '    echo "Log entry ${n}"',
            'done',
        ])
        logger = self.dh.containers.create(
            'logger', IMG, command=['sh', '-c', script])
        self.addCleanup(self.dh.containers.remove, logger, force=True)
        logger.start()
        logger.reload()
        return logger
