import socket
import struct
import threading
import unittest
from datetime import datetime

from seaworthy._lowlevel import stream_logs
from seaworthy.checks import docker_client, dockertest
from seaworthy.dockerhelper import DockerHelper, fetch_images
from seaworthy.logs import (
    EqualsMatcher, OrderedLinesMatcher, RegexMatcher, UnorderedLinesMatcher,
    stream_with_history, wait_for_logs_matching)

# We use this image to test with because it is a small (~4MB) image from
# https://github.com/docker-library/official-images that we can run shell
# scripts in.
IMG = 'alpine:latest'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    with docker_client() as client:
        fetch_images(client, [IMG])


class TestEqualsMatcher(unittest.TestCase):
    def test_matching(self):
        """ Matches exactly equal strings and nothing else. """
        matcher = EqualsMatcher('foo')
        self.assertTrue(matcher('foo'))
        self.assertFalse(matcher('foobar'))

    def test_str(self):
        """ The string representation is readable. """
        matcher = EqualsMatcher('bar')
        self.assertEqual(str(matcher), "EqualsMatcher('bar')")
        self.assertEqual(repr(matcher), str(matcher))


class TestRegexMatcher(unittest.TestCase):
    def test_matching(self):
        """
        Matches strings that match the pattern, doesn't match other strings.
        """
        matcher = RegexMatcher(r'^foo')
        self.assertTrue(matcher('foobar'))
        self.assertFalse(matcher('barfoo'))

    def test_str(self):
        """ The string representation is readable. """
        matcher = RegexMatcher(r'^bar')
        self.assertEqual(str(matcher), "RegexMatcher('^bar')")
        self.assertEqual(repr(matcher), str(matcher))


class TestOrderedLinesMatcher(unittest.TestCase):
    def test_matching(self):
        """
        Applies each matcher sequentially and returns True on the final match.
        """
        matcher = OrderedLinesMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertFalse(matcher('barfoo'))
        self.assertFalse(matcher('foo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('barfoo'))

    def test_by_equality(self):
        """
        The ``by_equality`` utility method takes a list of strings and produces
        a matcher that matches those strings by equality sequentially.
        """
        matcher = OrderedLinesMatcher.by_equality('foo', 'bar')

        self.assertFalse(matcher('bar'))
        self.assertFalse(matcher('foo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('bar'))

    def test_by_regex(self):
        """
        The ``by_regex`` utility method takes a list of patterns and produces a
        matcher that matches by those regex patterns sequentially.
        """
        matcher = OrderedLinesMatcher.by_regex(r'^foo', r'bar$')

        self.assertFalse(matcher('fuzzbar'))
        self.assertFalse(matcher('foobar'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('foobar'))

    def test_exhaustion(self):
        """
        Once all matchers have been matched, further calls to ``match`` should
        raise an error.
        """
        matcher = OrderedLinesMatcher.by_equality('foo')
        self.assertTrue(matcher('foo'))

        with self.assertRaises(RuntimeError) as cm:
            matcher('bar')
        self.assertEqual(str(cm.exception),
                         'Matcher exhausted, no more matchers to use')

    def test_str(self):
        """
        The string representation is readable and shows which matchers have
        been matched and which are still to be matched.
        """
        matcher = OrderedLinesMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertEqual(
            str(matcher),
            'OrderedLinesMatcher(matched=[], '
            "unmatched=[EqualsMatcher('foo'), RegexMatcher('^bar')])")
        self.assertEqual(repr(matcher), str(matcher))

        self.assertFalse(matcher('foo'))

        self.assertEqual(
            str(matcher),
            "OrderedLinesMatcher(matched=[EqualsMatcher('foo')], "
            "unmatched=[RegexMatcher('^bar')])")
        self.assertEqual(repr(matcher), str(matcher))

        self.assertTrue(matcher('barfoo'))

        self.assertEqual(
            str(matcher),
            "OrderedLinesMatcher(matched=[EqualsMatcher('foo'), "
            "RegexMatcher('^bar')], unmatched=[])")
        self.assertEqual(repr(matcher), str(matcher))


class TestUnorderedLinesMatcher(unittest.TestCase):
    def test_matching(self):
        """
        Applies each matcher sequentially and returns True on the final match.
        """
        matcher = UnorderedLinesMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertFalse(matcher('barfoo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('foo'))

        matcher = UnorderedLinesMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertFalse(matcher('foo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('barfoo'))

    def test_by_equality(self):
        """
        The ``by_equality`` utility method takes a list of strings and produces
        a matcher that matches those strings by equality sequentially.
        """
        matcher = UnorderedLinesMatcher.by_equality('foo', 'bar')

        self.assertFalse(matcher('foo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('bar'))

    def test_by_regex(self):
        """
        The ``by_regex`` utility method takes a list of patterns and produces a
        matcher that matches by those regex patterns sequentially.
        """
        matcher = UnorderedLinesMatcher.by_regex(r'^foo', r'bar$')

        self.assertFalse(matcher('foobar'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('foobar'))

    def test_exhaustion(self):
        """
        Once all matchers have been matched, further calls to ``match`` should
        raise an error.
        """
        matcher = UnorderedLinesMatcher.by_equality('foo')
        self.assertTrue(matcher('foo'))

        with self.assertRaises(RuntimeError) as cm:
            matcher('bar')
        self.assertEqual(str(cm.exception),
                         'Matcher exhausted, no more matchers to use')

    def test_str(self):
        """
        The string representation is readable and shows which matchers have
        been matched and which are still to be matched.
        """
        matcher = UnorderedLinesMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertEqual(
            str(matcher),
            'UnorderedLinesMatcher(matched=[], '
            "unmatched=[EqualsMatcher('foo'), RegexMatcher('^bar')])")
        self.assertEqual(repr(matcher), str(matcher))

        self.assertFalse(matcher('foo'))

        self.assertEqual(
            str(matcher),
            "UnorderedLinesMatcher(matched=[EqualsMatcher('foo')], "
            "unmatched=[RegexMatcher('^bar')])")
        self.assertEqual(repr(matcher), str(matcher))

        self.assertTrue(matcher('barfoo'))

        self.assertEqual(
            str(matcher),
            "UnorderedLinesMatcher(matched=[EqualsMatcher('foo'), "
            "RegexMatcher('^bar')], unmatched=[])")
        self.assertEqual(repr(matcher), str(matcher))


class FakeLogsContainer:
    """
    A container object stub that emits canned logs.

    Logs can either be streamed through a socket using ``.attach_socket()`` or
    tailed by using ``.logs()``. After a log entry has been streamed, it is
    stored and we don't stream it next time. Only logs that have already been
    streamed are tailed.
    """

    def __init__(self, log_entries, expected_params=None):
        self.log_entries = log_entries
        self._seen_logs = []
        self._expected_params = {
            'stdout': 1,
            'stderr': 1,
            'stream': 1,
            'logs': 0,
        }
        if expected_params is not None:
            self._expected_params.update(expected_params)
        self._feeder = None
        self._client_sockets = set()

    def cleanup(self):
        self.cancel_feeder()
        while self._client_sockets:
            self._client_sockets.pop().close()

    def cancel_feeder(self):
        feeder = self._feeder
        if feeder is not None:
            feeder.finished.set()
            feeder.join()

    def logs(self, stream=False, **kw):
        assert stream is False
        tail = kw.get('tail', 'all')
        if tail == 'all':
            tail = 0
        else:
            assert tail > 0
        return b''.join(self._seen_logs[-tail:])

    def attach_socket(self, params):
        assert self._feeder is None
        assert params == self._expected_params
        server, client = socket.socketpair()
        self._client_sockets.add(client)
        self._feeder = LogFeeder(self, server)
        fileobj = socket.SocketIO(client, 'rb')
        # The "socket" object we get back from the real attach_socket() method
        # has the real response object added to it like this so it doesn't get
        # garbage-collected too soon. We (ab)use that to properly close the
        # connection when we're done (to avoid leaks and ResourceWarnings), so
        # we need an equivalent in this fake. We do this before starting the
        # feeder to avoid races with really fast logs.
        fileobj._response = self._feeder
        self._feeder.start()
        return fileobj


class LogFeeder(threading.Thread):
    def __init__(self, container, sock):
        super().__init__()
        self.con = container
        self.sock = sock
        self.finished = threading.Event()

    def close(self):
        # This is a bit of a hack to avoid having a separate fake request
        # object for the streaming client to close when it's done.
        self.con.cleanup()

    def send_line(self, line):
        data = b'\x00\x00\x00\x00' + struct.pack('>L', len(line)) + line
        self.sock.send(data)

    def run(self):
        # Emit previously unstreamed lines at designated intervals.
        for delay, line in self.con.log_entries[len(self.con._seen_logs):]:
            # Wait for either cancelation (break) or timeout (no break).
            if self.finished.wait(delay):
                break
            self.con._seen_logs.append(line)
            self.send_line(line)
        # For whatever reason, we're done. Time to clean up.
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        self.con._feeder = None


class TestFakeLogsContainer(unittest.TestCase):
    def mkcontainer(self, *args, **kw):
        con = FakeLogsContainer(*args, **kw)
        self.addCleanup(con.cleanup)
        return con

    def stream(self, con, timeout=1):
        return list(stream_logs(con, timeout=timeout))

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
        have already been streamed are not returned again.

        NOTE: This test measures wall-clock time, so if something causes it to
              be too slow the second assertion may fail.
        """
        con = self.mkcontainer([(0.1, b'hello\n'), (0.2, b'goodbye\n')])
        t0 = datetime.now()
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        t1 = datetime.now()
        self.assertEqual(self.stream(con), [])
        t2 = datetime.now()
        self.assertLess(0.3, (t1 - t0).total_seconds())
        self.assertLess((t2 - t1).total_seconds(), 0.3)


class TestStreamWithHistoryFunc(unittest.TestCase):
    def mkcontainer(self, *args, **kw):
        con = FakeLogsContainer(*args, **kw)
        self.addCleanup(con.cleanup)
        return con

    def stream(self, con, timeout=1):
        return list(stream_logs(con, timeout=timeout))

    def swh(self, con, timeout=0.5, **kw):
        return stream_with_history(con, timeout=timeout, **kw)

    def test_stream_only(self):
        """
        If there are no historical logs, we get all the streamed logs.
        """
        con = self.mkcontainer([
            (0.1, b'hello\n'),
            (0.1, b'goodbye\n'),
        ])
        self.assertEqual(list(self.swh(con)), [b'hello\n', b'goodbye\n'])

    def test_historical_only(self):
        """
        If all the logs have been streamed, we only get the old ones.
        """
        con = self.mkcontainer([
            (0.1, b'hello\n'),
            (0.1, b'goodbye\n'),
        ])
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        self.assertEqual(self.stream(con), [])
        self.assertEqual(list(self.swh(con)), [b'hello\n', b'goodbye\n'])

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
            for line in self.swh(con, timeout=0.15):
                lines.append(line)
        self.assertEqual(lines, [b'hello\n'])
        lines = list(self.swh(con, timeout=0.25))
        self.assertEqual(lines, [b'hello\n', b'goodbye\n'])


class TestWaitForLogsMatchingFunc(unittest.TestCase):
    def mkcontainer(self, *args, **kw):
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
            for line in self.stream(logger, timeout=0.7):
                streamed_logs.append(line.decode('utf8').rstrip())
        self.assertNotIn('Log entry 1', streamed_logs)
        self.assertIn('Log entry 4', streamed_logs)
        self.assertNotIn('Log entry 9', streamed_logs)

        swh_logs = []
        for line in self.swh(logger, timeout=2):
            swh_logs.append(line.decode('utf8').rstrip())
        self.assertIn('Log entry 1', swh_logs)
        self.assertIn('Log entry 4', swh_logs)
        self.assertIn('Log entry 9', swh_logs)


class TestWithFakeContainer(unittest.TestCase, FakeAndRealContainerMixin):
    def mkcontainer(self, *args, **kw):
        con = FakeLogsContainer(*args, **kw)
        self.addCleanup(con.cleanup)
        return con

    def start_logging_container(self):
        return self.mkcontainer([
            (0.2, 'Log entry {}\n'.format(n).encode('utf8'))
            for n in range(10)])

    def wflm(self, con, matcher, timeout=0.5, **kw):
        return wait_for_logs_matching(con, matcher, timeout=timeout, **kw)

    def stream(self, con, timeout=1):
        for line in stream_logs(con, timeout=timeout):
            yield line

    def swh(self, con, timeout=0.5, **kw):
        for line in stream_with_history(con, timeout=timeout, **kw):
            yield line


@dockertest()
class TestWithRealContainer(unittest.TestCase, FakeAndRealContainerMixin):
    def setUp(self):
        self.dh = DockerHelper()
        self.addCleanup(self.dh.teardown)
        self.dh.setup()

    def start_logging_container(self):
        script = '\n'.join([
            'for n in 0 1 2 3 4 5 6 7 8 9; do',
            '    sleep 0.2',
            '    echo "Log entry ${n}"',
            'done',
        ])
        logger = self.dh.create_container(
            'logger', IMG, command=['sh', '-c', script])
        self.addCleanup(self.dh.stop_and_remove_container, logger)
        self.dh.start_container(logger)
        return logger

    def wflm(self, con, matcher, timeout=0.5, **kw):
        return wait_for_logs_matching(con, matcher, timeout=timeout, **kw)

    def stream(self, con, timeout=1):
        for line in stream_logs(con, timeout=timeout):
            yield line

    def swh(self, con, timeout=0.5, **kw):
        for line in stream_with_history(con, timeout=timeout, **kw):
            yield line
