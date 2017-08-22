import unittest
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
    """

    def __init__(self, log_entries, expected_kw=None):
        self.log_entries = log_entries
        self._seen_logs = []
        self.expected_kw = {} if expected_kw is None else expected_kw

    def logs(self, stream=False, **kw):
        if stream:
            assert kw == self.expected_kw
            return self.iter_logs()
        assert kw['tail'] > 0
        return b''.join(self._seen_logs[-kw['tail']:])

    def iter_logs(self):
        self._seen_logs = []
        for wait, line in self.log_entries:
            sleep(wait)
            self._seen_logs.append(line)
            yield line


class TestWaitForLogsMatchingFunc(unittest.TestCase):
    def test_one_matching_line(self):
        """
        If one matching line is logged, all is happy.
        """
        con = FakeLogsContainer([
            (0, b'hello\n'),
        ])
        # If this doesn't raise an exception, the test passes.
        wait_for_logs_matching(con, EqualsMatcher('hello'), timeout=0.001)

    def test_one_non_matching_line(self):
        """
        If there's no match by the time the logs end, we raise an exception.
        """
        con = FakeLogsContainer([
            (0, b'goodbye\n'),
        ])
        with self.assertRaises(RuntimeError) as cm:
            wait_for_logs_matching(con, EqualsMatcher('hello'), timeout=0.001)
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
            wait_for_logs_matching(con, EqualsMatcher('hello'), timeout=1)
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
            wait_for_logs_matching(con, EqualsMatcher('hello'), timeout=0.001)
        self.assertIn(
            "Timeout waiting for logs matching EqualsMatcher('hello').",
            str(cm.exception))
        self.assertIn('hi\n', str(cm.exception))
        self.assertNotIn('hello\n', str(cm.exception))
