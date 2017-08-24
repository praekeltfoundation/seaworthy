"""
Tools for waiting on and matching log lines from a container.
"""

import re

from ._lowlevel import stream_logs


def _last_few_log_lines(container, max_lines=100):
    logs = container.logs(tail=max_lines).decode('utf-8')
    return '\nLast few log lines:\n{}'.format(logs)


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
        for line in stream_logs(container, timeout=timeout, **logs_kwargs):
            # Drop the trailing newline
            line = line.decode(encoding).rstrip()
            if matcher(line):
                return line
    except TimeoutError:
        raise TimeoutError('Timeout waiting for logs matching {}.{}'.format(
            matcher, _last_few_log_lines(container)))

    raise RuntimeError('Logs matching {} not found.{}'.format(
        matcher, _last_few_log_lines(container)))


class SequentialLinesMatcher(object):
    """
    Matcher that takes a list of matchers, and uses one after the next after
    each has a successful match. Returns True ("matches") on the final match.

    **Note:** This is a *stateful* matcher. Once it has done its matching,
    you'll need to create a new instance.
    """
    def __init__(self, *matchers):
        self._matchers = matchers
        self._position = 0

    @classmethod
    def by_equality(cls, *rhs):
        return SequentialLinesMatcher(*map(EqualsMatcher, rhs))

    @classmethod
    def by_regex(cls, *patterns):
        return SequentialLinesMatcher(*map(RegexMatcher, patterns))

    def __call__(self, line):
        if self._position == len(self._matchers):
            raise RuntimeError('Matcher exhausted, no more matchers to use')

        matcher = self._matchers[self._position]
        if matcher(line):
            self._position += 1

        if self._position == len(self._matchers):
            # All patterns have been matched
            return True

        return False

    def __str__(self):
        matched = [str(m) for m in self._matchers[:self._position]]
        unmatched = [str(m) for m in self._matchers[self._position:]]
        return 'SequentialLinesMatcher(matched=[{}], unmatched=[{}])'.format(
            ', '.join(matched), ', '.join(unmatched))


class EqualsMatcher(object):
    """
    Matcher that matches log lines by equality.
    """
    def __init__(self, rhs):
        self._rhs = rhs

    def __call__(self, lhs):
        return lhs == self._rhs

    def __str__(self):
        return 'EqualsMatcher({!r})'.format(self._rhs)


class RegexMatcher(object):
    """
    Matcher that matches log lines by regex pattern.
    """
    def __init__(self, pattern):
        self._regex = re.compile(pattern)

    def __call__(self, line):
        return self._regex.search(line) is not None

    def __str__(self):
        return 'RegexMatcher({!r})'.format(self._regex.pattern)


__all__ = ['EqualsMatcher', 'RegexMatcher', 'SequentialLinesMatcher',
           'wait_for_logs_matching']
