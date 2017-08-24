import socket
import struct
import threading
import unittest
from datetime import datetime

from seaworthy._lowlevel import stream_logs
from seaworthy.logs import (
    EqualsMatcher, RegexMatcher, SequentialLinesMatcher,
    wait_for_logs_matching)


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


class TestSequentialLinesMatcher(unittest.TestCase):
    def test_matching(self):
        """
        Applies each matcher sequentially and returns True on the final match.
        """
        matcher = SequentialLinesMatcher(
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
        matcher = SequentialLinesMatcher.by_equality('foo', 'bar')

        self.assertFalse(matcher('bar'))
        self.assertFalse(matcher('foo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('bar'))

    def test_by_regex(self):
        """
        The ``by_regex`` utility method takes a list of patterns and produces a
        matcher that matches by those regex patterns sequentially.
        """
        matcher = SequentialLinesMatcher.by_regex(r'^foo', r'bar$')

        self.assertFalse(matcher('fuzzbar'))
        self.assertFalse(matcher('foobar'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('foobar'))

    def test_exhaustion(self):
        """
        Once all matchers have been matched, further calls to ``match`` should
        raise an error.
        """
        matcher = SequentialLinesMatcher.by_equality('foo')
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
        matcher = SequentialLinesMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertEqual(
            str(matcher),
            'SequentialLinesMatcher(matched=[], '
            "unmatched=[EqualsMatcher('foo'), RegexMatcher('^bar')])")

        self.assertFalse(matcher('foo'))

        self.assertEqual(
            str(matcher),
            "SequentialLinesMatcher(matched=[EqualsMatcher('foo')], "
            "unmatched=[RegexMatcher('^bar')])")

        self.assertTrue(matcher('barfoo'))

        self.assertEqual(
            str(matcher),
            "SequentialLinesMatcher(matched=[EqualsMatcher('foo'), "
            "RegexMatcher('^bar')], unmatched=[])")


class FakeLogsContainer:
    """
    A container object stub that emits canned logs.

    Logs can either be streamed through a socket using ``.attach_socket()`` or
    tailed by using ``.logs()``. After a log entry has been streamed, it is
    stored and we don't wait for it next time. Only logs that have already been
    streamed are tailed.
    """

    def __init__(self, log_entries, expected_params=None):
        self.log_entries = log_entries
        self._seen_logs = []
        self._expected_params = {
            'stdout': 1,
            'stderr': 1,
            'stream': 1,
            'logs': 1,
        }
        if expected_params is not None:
            self._expected_params.update(expected_params)
        self._feeder = None

    def cleanup(self):
        if self._feeder is not None:
            self._feeder.cancel()
            self._feeder = None

    def logs(self, stream=False, **kw):
        assert stream is False
        tail = kw.get('tail', 'all')
        if tail == 'all':
            tail = len(self._seen_logs)
        assert tail > 0
        return b''.join(self._seen_logs[-tail:])

    def attach_socket(self, params):
        assert self._feeder is None
        assert params == self._expected_params
        server, client = socket.socketpair()
        self._feeder = LogFeeder(self, server)
        self._feeder.start()
        return socket.SocketIO(client, 'rb')


class LogFeeder(threading.Thread):
    def __init__(self, container, sock):
        super().__init__()
        self.con = container
        self.sock = sock
        self.finished = threading.Event()

    def cancel(self):
        self.finished.set()
        self.sock.close()

    def send_line(self, line):
        data = b'\x00\x00\x00\x00' + struct.pack('>L', len(line)) + line
        self.sock.send(data)

    def run(self):
        for line in self.con._seen_logs:
            self.send_line(line)
        for delay, line in self.con.log_entries[len(self.con._seen_logs):]:
            # Wait for either cancelation (break) or timeout (no break).
            if self.finished.wait(delay):
                break
            self.con._seen_logs.append(line)
            self.send_line(line)
        self.con.cleanup()


class TestFakeLogsContainer(unittest.TestCase):
    def stream(self, con, timeout=1):
        # Always clean up the feeder machinery when we're done. This is only
        # necessary if we timed out, but it doesn't hurt to clean up an
        # already-clean FakeLogsContainer.
        try:
            return list(stream_logs(con, timeout=timeout))
        finally:
            con.cleanup()

    def test_empty(self):
        """
        Streaming logs for a container with no logs returns immediately.
        """
        con = FakeLogsContainer([])
        self.assertEqual(self.stream(con), [])
        self.assertEqual(con.logs(tail=1), b'')

    def test_tail_only_returns_streamed(self):
        """
        Only logs that have been streamed can be tailed.
        """
        con = FakeLogsContainer([(0, b'hello\n'), (0, b'goodbye\n')])
        self.assertEqual(con.logs(tail=2), b'')
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        self.assertEqual(con.logs(tail=2), b'hello\ngoodbye\n')

    def test_tail_tails(self):
        """
        Tailing returns the last N log lines, or all line if there are fewer
        than N or if N is 'all' (which is the default).
        """
        con = FakeLogsContainer([(0, b'hello\n'), (0, b'goodbye\n')])
        self.stream(con)
        self.assertEqual(con.logs(tail=1), b'goodbye\n')
        self.assertEqual(con.logs(tail=2), b'hello\ngoodbye\n')
        self.assertEqual(con.logs(tail=3), b'hello\ngoodbye\n')
        self.assertEqual(con.logs(tail='all'), b'hello\ngoodbye\n')
        self.assertEqual(con.logs(), b'hello\ngoodbye\n')

    def test_streaming_waits(self):
        """
        Streamed logs will be returned at specified intervals. Any logs that
        have already been streamed are returned immediately when streamed
        subsequently.

        NOTE: This test measures wall-clock time, so if something causes it to
              be too slow the second assertion may fail.
        """
        con = FakeLogsContainer([(0.1, b'hello\n'), (0.2, b'goodbye\n')])
        t0 = datetime.now()
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        t1 = datetime.now()
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        t2 = datetime.now()
        self.assertLess(0.3, (t1 - t0).total_seconds())
        self.assertLess((t2 - t1).total_seconds(), 0.3)


class TestWaitForLogsMatchingFunc(unittest.TestCase):
    def mkcontainer(self, *args, **kw):
        con = FakeLogsContainer(*args, **kw)
        self.addCleanup(con.cleanup)
        return con

    def wflm(self, con, matcher, timeout=0.5, **kw):
        # Always clean up the feeder machinery when we're done. This is only
        # necessary if we timed out, but it doesn't hurt to clean up an
        # already-clean FakeLogsContainer.
        try:
            return wait_for_logs_matching(con, matcher, timeout=timeout, **kw)
        finally:
            con.cleanup()

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
            "Timeout waiting for logs matching EqualsMatcher('hello').",
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
            "Timeout waiting for logs matching EqualsMatcher('hello').",
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
