import unittest

from seaworthy.stream.matchers import (
    EqualsMatcher, OrderedMatcher, RegexMatcher, UnorderedMatcher)


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


class TestOrderedMatcher(unittest.TestCase):
    def test_matching(self):
        """
        Applies each matcher sequentially and returns True on the final match.
        """
        matcher = OrderedMatcher(
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
        matcher = OrderedMatcher.by_equality('foo', 'bar')

        self.assertFalse(matcher('bar'))
        self.assertFalse(matcher('foo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('bar'))

    def test_by_regex(self):
        """
        The ``by_regex`` utility method takes a list of patterns and produces a
        matcher that matches by those regex patterns sequentially.
        """
        matcher = OrderedMatcher.by_regex(r'^foo', r'bar$')

        self.assertFalse(matcher('fuzzbar'))
        self.assertFalse(matcher('foobar'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('foobar'))

    def test_exhaustion(self):
        """
        Once all matchers have been matched, further calls to ``match`` should
        raise an error.
        """
        matcher = OrderedMatcher.by_equality('foo')
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
        matcher = OrderedMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertEqual(
            str(matcher),
            'OrderedMatcher(matched=[], '
            "unmatched=[EqualsMatcher('foo'), RegexMatcher('^bar')])")
        self.assertEqual(repr(matcher), str(matcher))

        self.assertFalse(matcher('foo'))

        self.assertEqual(
            str(matcher),
            "OrderedMatcher(matched=[EqualsMatcher('foo')], "
            "unmatched=[RegexMatcher('^bar')])")
        self.assertEqual(repr(matcher), str(matcher))

        self.assertTrue(matcher('barfoo'))

        self.assertEqual(
            str(matcher),
            "OrderedMatcher(matched=[EqualsMatcher('foo'), "
            "RegexMatcher('^bar')], unmatched=[])")
        self.assertEqual(repr(matcher), str(matcher))


class TestUnorderedMatcher(unittest.TestCase):
    def test_matching(self):
        """
        Applies each matcher sequentially and returns True on the final match.
        """
        matcher = UnorderedMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertFalse(matcher('barfoo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('foo'))

        matcher = UnorderedMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertFalse(matcher('foo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('barfoo'))

    def test_by_equality(self):
        """
        The ``by_equality`` utility method takes a list of strings and produces
        a matcher that matches those strings by equality sequentially.
        """
        matcher = UnorderedMatcher.by_equality('foo', 'bar')

        self.assertFalse(matcher('foo'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('bar'))

    def test_by_regex(self):
        """
        The ``by_regex`` utility method takes a list of patterns and produces a
        matcher that matches by those regex patterns sequentially.
        """
        matcher = UnorderedMatcher.by_regex(r'^foo', r'bar$')

        self.assertFalse(matcher('foobar'))
        self.assertFalse(matcher('baz'))
        self.assertTrue(matcher('foobar'))

    def test_exhaustion(self):
        """
        Once all matchers have been matched, further calls to ``match`` should
        raise an error.
        """
        matcher = UnorderedMatcher.by_equality('foo')
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
        matcher = UnorderedMatcher(
            EqualsMatcher('foo'), RegexMatcher('^bar'))

        self.assertEqual(
            str(matcher),
            'UnorderedMatcher(matched=[], '
            "unmatched=[EqualsMatcher('foo'), RegexMatcher('^bar')])")
        self.assertEqual(repr(matcher), str(matcher))

        self.assertFalse(matcher('foo'))

        self.assertEqual(
            str(matcher),
            "UnorderedMatcher(matched=[EqualsMatcher('foo')], "
            "unmatched=[RegexMatcher('^bar')])")
        self.assertEqual(repr(matcher), str(matcher))

        self.assertTrue(matcher('barfoo'))

        self.assertEqual(
            str(matcher),
            "UnorderedMatcher(matched=[EqualsMatcher('foo'), "
            "RegexMatcher('^bar')], unmatched=[])")
        self.assertEqual(repr(matcher), str(matcher))
