import re
from abc import ABC, abstractmethod


class StreamMatcher(ABC):
    """
    Abstract base class for stream matchers.
    """

    @abstractmethod
    def match(self, item):
        """
        Return ``True`` if the matcher matches an item, otherwise ``False``.
        """

    @abstractmethod
    def args_str(self):
        """
        Return an args string for the repr.
        """

    def __call__(self, item):
        return self.match(item)

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.args_str())

    def __repr__(self):
        return str(self)


def to_matcher(matcher_factory, obj):
    """
    Turn an object into a :class:`StreamMatcher` unless it already is one.

    :param matcher_factory: A callable capable of turning `obj` into a
        :class:`StreamMatcher`.
    :param obj: A :class:`StreamMatcher` or an object to turn into one.

    :returns: :class:`StreamMatcher`
    """
    return obj if isinstance(obj, StreamMatcher) else matcher_factory(obj)


class CombinationMatcher(StreamMatcher):
    """
    Matcher that combines multiple input matchers.
    """
    def __init__(self, *matchers):
        self._matchers = matchers

    @classmethod
    def by_equality(cls, *expected_items):
        """
        Construct an instance of this combination matcher from a list of
        expected items and/or StreamMatcher instances.
        """
        return cls(*(to_matcher(EqualsMatcher, i) for i in expected_items))

    @classmethod
    def by_regex(cls, *patterns):
        """
        Construct an instance of this combination matcher from a list of
        regex patterns and/or StreamMatcher instances.
        """
        return cls(*(to_matcher(RegexMatcher, p) for p in patterns))


class OrderedMatcher(CombinationMatcher):
    """
    Matcher that takes a list of matchers, and uses one after the next after
    each has a successful match. Returns True ("matches") on the final match.

    **Note:** This is a *stateful* matcher. Once it has done its matching,
    you'll need to create a new instance.
    """
    def __init__(self, *matchers):
        super().__init__(*matchers)
        self._position = 0

    def match(self, item):
        """
        Return ``True`` if the expected matchers are matched in the expected
        order, otherwise ``False``.
        """
        if self._position == len(self._matchers):
            raise RuntimeError('Matcher exhausted, no more matchers to use')

        matcher = self._matchers[self._position]
        if matcher(item):
            self._position += 1

        if self._position == len(self._matchers):
            # All patterns have been matched
            return True

        return False

    def args_str(self):
        """
        Return an args string for the repr.
        """
        matched = [str(m) for m in self._matchers[:self._position]]
        unmatched = [str(m) for m in self._matchers[self._position:]]
        return 'matched=[{}], unmatched=[{}]'.format(
            ', '.join(matched), ', '.join(unmatched))


class UnorderedMatcher(CombinationMatcher):
    """
    Matcher that takes a list of matchers, and matches each one to an item.
    Each item is tested against each unmatched matcher until a match is found
    or all unmatched matchers are checked. Returns True ("matches") on the
    final match.

    .. note::

        This is a *stateful* matcher. Once it has done its matching,
        you'll need to create a new instance.
    """
    def __init__(self, *matchers):
        super().__init__(*matchers)
        self._used_matchers = []

    @property
    def _unused_matchers(self):
        return [m for m in self._matchers if m not in self._used_matchers]

    def match(self, item):
        """
        Return ``True`` if the expected matchers are matched in any order,
        otherwise ``False``.
        """
        if not self._unused_matchers:
            raise RuntimeError('Matcher exhausted, no more matchers to use')

        for matcher in self._unused_matchers:
            if matcher(item):
                self._used_matchers.append(matcher)
                break

        if not self._unused_matchers:
            # All patterns have been matched
            return True

        return False

    def args_str(self):
        """
        Return an args string for the repr.
        """
        matched = [str(m) for m in self._used_matchers]
        unmatched = [str(m) for m in self._unused_matchers]
        return 'matched=[{}], unmatched=[{}]'.format(
            ', '.join(matched), ', '.join(unmatched))


class EqualsMatcher(StreamMatcher):
    """
    Matcher that matches items by equality.
    """
    def __init__(self, expected_item):
        self._expected_item = expected_item

    def match(self, item):
        """
        Return ``True`` if the item matches the expected value exactly,
        otherwise ``False``.
        """
        return item == self._expected_item

    def args_str(self):
        """
        Return an args string for the repr.
        """
        return repr(self._expected_item)


class RegexMatcher(StreamMatcher):
    """
    Matcher that matches items by regex pattern.
    """
    def __init__(self, pattern):
        self._regex = re.compile(pattern)

    def match(self, item):
        """
        Return ``True`` if the item matches the expected regex, otherwise
        ``False``.
        """
        return self._regex.search(item) is not None

    def args_str(self):
        """
        Return an args string for the repr.
        """
        return repr(self._regex.pattern)
