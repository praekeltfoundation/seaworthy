"""
Tools for waiting on and matching log lines from a container.
"""

import re
from abc import ABC, abstractmethod

from docker.models.containers import ExecResult

from ._lowlevel import stream_logs


def output_lines(output, encoding='utf-8'):
    """
    Convert bytestring container output or the result of a container exec
    command into a sequence of unicode lines.

    :param output:
        Container output bytes or an
        :class:`docker.models.containers.ExecResult` instance.
    :param encoding: The encoding to use when converting bytes to unicode
        (default ``utf-8``).

    :returns: list[str]
    """
    if isinstance(output, ExecResult):
        _, output = output

    return output.decode(encoding).splitlines()


def _last_few_log_lines(container):
    return container.logs(tail=100).decode('utf-8')


def wait_for_logs_matching(container, matcher, timeout=10, encoding='utf-8',
                           **logs_kwargs):
    """
    Wait for matching log line(s) from the given container by streaming the
    container's stdout and/or stderr outputs.

    Each log line is decoded and any trailing whitespace is stripped before the
    line is matched.

    :param ~docker.models.containers.Container container:
        Container who's log lines to wait for.
    :param matcher:
        Callable that returns True once it has matched a decoded log line(s).
    :param timeout:
        Timeout value in seconds.
    :param encoding:
        Encoding to use when decoding container output to strings.
    :param logs_kwargs:
        Additional keyword arguments to pass to ``container.logs()``. For
        example, the ``stdout`` and ``stderr`` boolean arguments can be used to
        determine whether to stream stdout or stderr or both (the default).

    :returns:
        The final matching log line.
    :raises TimeoutError:
        When the timeout value is reached before matching log lines have been
        found.
    :raises RuntimeError:
        When all log lines have been consumed but matching log lines have not
        been found (the container must have stopped for its stream to have
        ended without error).
    """
    try:
        for line in stream_logs(
                container, timeout=timeout, **logs_kwargs):
            # Drop the trailing newline
            line = line.decode(encoding).rstrip()
            if matcher(line):
                return line
    except TimeoutError:
        raise TimeoutError('\n'.join([
            ('Timeout ({}s) waiting for logs matching {}.'.format(
                timeout, matcher)),
            'Last few log lines:',
            _last_few_log_lines(container),
        ]))

    raise RuntimeError('\n'.join([
        'Logs matching {} not found.'.format(matcher),
        'Last few log lines:',
        _last_few_log_lines(container),
    ]))


class LogMatcher(ABC):
    """
    Abstract base class for log matchers.
    """

    @abstractmethod
    def match(self, log_line):
        """
        Return ``True`` if the matcher matches a line, otherwise ``False``.
        """

    @abstractmethod
    def args_str(self):
        """
        Return an args string for the repr.
        """

    def __call__(self, log_line):
        return self.match(log_line)

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.args_str())

    def __repr__(self):
        return str(self)


def to_matcher(matcher_factory, obj):
    """
    Turn an object into a :class:`LogMatcher` unless it already is one.

    :param matcher_factory: A callable capable of turning `obj` into a
        :class:`LogMatcher`.
    :param obj: A :class:`LogMatcher` or an object to turn into one.

    :returns: :class:`LogMatcher`
    """
    return obj if isinstance(obj, LogMatcher) else matcher_factory(obj)


class CombinationLogMatcher(LogMatcher):
    """
    Matcher that combines multiple input matchers.
    """
    def __init__(self, *matchers):
        self._matchers = matchers

    @classmethod
    def by_equality(cls, *expected_lines):
        """
        Construct an instance of this combination matcher from a list of
        expected log lines and/or LogMatcher instances.
        """
        return cls(*(to_matcher(EqualsMatcher, l) for l in expected_lines))

    @classmethod
    def by_regex(cls, *patterns):
        """
        Construct an instance of this combination matcher from a list of
        regex patterns and/or LogMatcher instances.
        """
        return cls(*(to_matcher(RegexMatcher, p) for p in patterns))


class OrderedLinesMatcher(CombinationLogMatcher):
    """
    Matcher that takes a list of matchers, and uses one after the next after
    each has a successful match. Returns True ("matches") on the final match.

    **Note:** This is a *stateful* matcher. Once it has done its matching,
    you'll need to create a new instance.
    """
    def __init__(self, *matchers):
        super().__init__(*matchers)
        self._position = 0

    def match(self, log_line):
        """
        Return ``True`` if the expected matchers are matched in the expected
        order, otherwise ``False``.
        """
        if self._position == len(self._matchers):
            raise RuntimeError('Matcher exhausted, no more matchers to use')

        matcher = self._matchers[self._position]
        if matcher(log_line):
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


class UnorderedLinesMatcher(CombinationLogMatcher):
    """
    Matcher that takes a list of matchers, and matches each one to a line. Each
    line is tested against each unmatched matcher until a match is found or all
    unmatched matchers are checked. Returns True ("matches") on the final
    match.

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

    def match(self, log_line):
        """
        Return ``True`` if the expected matchers are matched in any order,
        otherwise ``False``.
        """
        if not self._unused_matchers:
            raise RuntimeError('Matcher exhausted, no more matchers to use')

        for matcher in self._unused_matchers:
            if matcher(log_line):
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


class EqualsMatcher(LogMatcher):
    """
    Matcher that matches log lines by equality.
    """
    def __init__(self, expected_line):
        self._expected_line = expected_line

    def match(self, log_line):
        """
        Return ``True`` if the log line matches the expected value exactly,
        otherwise ``False``.
        """
        return log_line == self._expected_line

    def args_str(self):
        """
        Return an args string for the repr.
        """
        return repr(self._expected_line)


class RegexMatcher(LogMatcher):
    """
    Matcher that matches log lines by regex pattern.
    """
    def __init__(self, pattern):
        self._regex = re.compile(pattern)

    def match(self, log_line):
        """
        Return ``True`` if the log line matches the expected regex, otherwise
        ``False``.
        """
        return self._regex.search(log_line) is not None

    def args_str(self):
        """
        Return an args string for the repr.
        """
        return repr(self._regex.pattern)


# Members of this module are documented in the order they appear here.
__all__ = [
    # Matchers
    'LogMatcher',

    'CombinationLogMatcher',
    'EqualsMatcher',
    'RegexMatcher',
    'OrderedLinesMatcher',
    'UnorderedLinesMatcher',

    # Functions
    'output_lines',
    'to_matcher',
    'wait_for_logs_matching',
]
