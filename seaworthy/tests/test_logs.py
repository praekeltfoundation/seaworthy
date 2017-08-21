from unittest import TestCase

from seaworthy.logs import (
    EqualsMatcher, PatternMatcher, SequentialLinesMatcher)


class TestEqualsMatcher(TestCase):
    def test_matching(self):
        """ Matches exactly equal strings and nothing else. """
        matcher = EqualsMatcher('foo')
        self.assertTrue(matcher('foo'))
        self.assertFalse(matcher('foobar'))

    def test_str(self):
        """ The string representation is readable. """
        matcher = EqualsMatcher('bar')
        self.assertEqual(str(matcher), "EqualsMatcher('bar')")


class TestPatternMatcher(TestCase):
    def test_matching(self):
        """
        Matches strings that match the pattern, doesn't match other strings.
        """
        matcher = PatternMatcher(r'^foo')
        self.assertTrue(matcher('foobar'))
        self.assertFalse(matcher('barfoo'))

    def test_str(self):
        """ The string representation is readable. """
        matcher = PatternMatcher(r'^bar')
        self.assertEqual(str(matcher), "PatternMatcher('^bar')")


class TestSequentialLinesMatcher(TestCase):
    def test_matching(self):
        """
        Applies each matcher sequentially and returns True on the final match.
        """
        matcher = SequentialLinesMatcher(
            EqualsMatcher('foo'), PatternMatcher('^bar'))

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

    def test_by_patterns(self):
        """
        The ``by_patterns`` utility method takes a list of patterns and
        produces a matcher that matches by those patterns sequentially.
        """
        matcher = SequentialLinesMatcher.by_patterns(r'^foo', r'bar$')

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
            EqualsMatcher('foo'), PatternMatcher('^bar'))

        self.assertEqual(
            str(matcher),
            'SequentialLinesMatcher(matched=[], '
            "unmatched=[EqualsMatcher('foo'), PatternMatcher('^bar')])")

        self.assertFalse(matcher('foo'))

        self.assertEqual(
            str(matcher),
            "SequentialLinesMatcher(matched=[EqualsMatcher('foo')], "
            "unmatched=[PatternMatcher('^bar')])")

        self.assertTrue(matcher('barfoo'))

        self.assertEqual(
            str(matcher),
            "SequentialLinesMatcher(matched=[EqualsMatcher('foo'), "
            "PatternMatcher('^bar')], unmatched=[])")
