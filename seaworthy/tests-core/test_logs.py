import unittest
from datetime import datetime
from time import sleep

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

    Logs can either be streamed or tailed. After a log entry has been streamed,
    it is stored and we don't wait for it next time. Only logs that have
    already been streamed are tailed.
    """

    def __init__(self, log_entries, expected_kw=None):
        self.log_entries = log_entries
        self._seen_logs = []
        self._expected_kw = {} if expected_kw is None else expected_kw

    def logs(self, stream=False, **kw):
        if stream:
            # We're streaming logs, so return our iterator.
            assert kw == self._expected_kw
            return self.iter_logs()
        # We're not streaming logs, make sure we're tailing them.
        tail = kw.get('tail', 'all')
        if tail == 'all':
            tail = len(self._seen_logs)
        assert tail > 0
        return b''.join(self._seen_logs[-tail:])

    def iter_logs(self):
        for line in self._seen_logs:
            yield line
        for wait, line in self.log_entries[len(self._seen_logs):]:
            sleep(wait)
            self._seen_logs.append(line)
            yield line


class TestFakeLogsContainer(unittest.TestCase):
    def stream(self, con):
        return list(con.logs(stream=True))

    def test_empty(self):
        """
        Streaming logs for a container with no logs returns immediately.
        """
        con = FakeLogsContainer([])
        self.assertEqual(list(con.logs(stream=True)), [])
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
        con = FakeLogsContainer([(0.01, b'hello\n'), (0.02, b'goodbye\n')])
        t0 = datetime.now()
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        t1 = datetime.now()
        self.assertEqual(self.stream(con), [b'hello\n', b'goodbye\n'])
        t2 = datetime.now()
        self.assertLess(0.03, (t1 - t0).total_seconds())
        self.assertLess((t2 - t1).total_seconds(), 0.03)


class TestWaitForLogsMatchingFunc(unittest.TestCase):
    def wflm(self, container, matcher, timeout=0.5, **kw):
        return wait_for_logs_matching(container, matcher, timeout=timeout, **kw)

    def test_one_matching_line(self):
        """
        If one matching line is logged, all is happy.
        """
        con = FakeLogsContainer([
            (0, b'hello\n'),
        ])
        # If this doesn't raise an exception, the test passes.
        self.wflm(con, EqualsMatcher('hello'))

    def test_one_non_matching_line(self):
        """
        If there's no match by the time the logs end, we raise an exception.
        """
        con = FakeLogsContainer([
            (0, b'goodbye\n'),
        ])
        with self.assertRaises(RuntimeError) as cm:
            self.wflm(con, EqualsMatcher('hello'))
        self.assertIn(
            "Logs matching EqualsMatcher('hello') not found.",
            str(cm.exception))
        self.assertIn('goodbye\n', str(cm.exception))

    @unittest.skip('This timeout stuff is currently broken.')
    def test_timeout_first_line(self):
        """
        If we take too long to get the first line, we time out.
        """
        con = FakeLogsContainer([
            (2, b'hello\n'),
        ])
        with self.assertRaises(TimeoutError) as cm:
            self.wflm(con, EqualsMatcher('hello'), timeout=1)
        self.assertIn(
            "Timeout waiting for logs matching EqualsMatcher('hello').",
            str(cm.exception))
        self.assertNotIn('hello\n', str(cm.exception))

    @unittest.skip('This timeout stuff is currently broken.')
    def test_timeout_later_line(self):
        """
        If we take too long to get a later line, we time out.
        """
        con = FakeLogsContainer([
            (0, b'hi\n'),
            (0.01, b'hello\n'),
        ])
        with self.assertRaises(TimeoutError) as cm:
            self.wflm(con, EqualsMatcher('hello'), timeout=0.001)
        self.assertIn(
            "Timeout waiting for logs matching EqualsMatcher('hello').",
            str(cm.exception))
        self.assertIn('hi\n', str(cm.exception))
        self.assertNotIn('hello\n', str(cm.exception))

    def test_default_encoding(self):
        """
        By default, we assume logs are UTF-8.
        """
        con = FakeLogsContainer([
            (0, b'\xc3\xbeorn\n'),
        ])
        # If this doesn't raise an exception, the test passes.
        self.wflm(con, EqualsMatcher('\u00feorn'))

    def test_encoding(self):
        """
        We can operate on logs that use excitingly horrible encodings.
        """
        con = FakeLogsContainer([
            (0, b'\xfeorn\n'),
        ])
        # If this doesn't raise an exception, the test passes.
        self.wflm(con, EqualsMatcher('\u00feorn'), encoding='latin1')
