"""
Tools for waiting on and matching log lines from a container.
"""

import re
from abc import ABC, abstractmethod

from ._lowlevel import stream_logs


def _last_few_log_lines(container, max_lines=100):
    logs = container.logs(tail=max_lines).decode('utf-8')
    return '\nLast few log lines:\n{}'.format(logs)


def stream_with_history(container, timeout=10, **logs_kwargs):
    """
    Return an iterator over all container logs, past and future.

    The docker API we use in stream_logs() doesn't *reliably* give us old logs
    (they're usually there, but sometimes they just aren't), and the docker API
    container.logs() uses seems to sometimes block indefinitely on the last few
    lines. To get around these issues, we fetch all the historical logs using
    one of the APIs before we start streaming the new logs with the other.
    """
    # Ignore the `stream` kwarg, because we handle that ourselves.
    logs_kwargs.pop('stream', None)
    # Start streaming immediately after fetching the old logs to minimise the
    # chance of a race condition.
    old_logs = container.logs(**logs_kwargs)
    stream = stream_logs(container, timeout=timeout, **logs_kwargs)
    # To make sure old logs match new, we keep the newlines we split on.
    for line in old_logs.splitlines(keepends=True):
        yield line
    yield from stream


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
        for line in stream_with_history(
                container, timeout=timeout, **logs_kwargs):
            # Drop the trailing newline
            line = line.decode(encoding).rstrip()
            if matcher(line):
                return line
    except TimeoutError:
        raise TimeoutError('Timeout waiting for logs matching {}.{}'.format(
            matcher, _last_few_log_lines(container)))

    raise RuntimeError('Logs matching {} not found.{}'.format(
        matcher, _last_few_log_lines(container)))


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


class SequentialLinesMatcher(LogMatcher):
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
    def by_equality(cls, *expected_lines):
        return cls(*map(EqualsMatcher, expected_lines))

    @classmethod
    def by_regex(cls, *patterns):
        return cls(*map(RegexMatcher, patterns))

    def match(self, log_line):
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
        matched = [str(m) for m in self._matchers[:self._position]]
        unmatched = [str(m) for m in self._matchers[self._position:]]
        return 'matched=[{}], unmatched=[{}]'.format(
            ', '.join(matched), ', '.join(unmatched))


class AnyOrderLinesMatcher(LogMatcher):
    """
    Matcher that takes a list of matchers, and matches each one to a line. Each
    line is tested against each unmatched matcher until a match is found or all
    unmatched matchers are checked. Returns True ("matches") on the final
    match.

    **Note:** This is a *stateful* matcher. Once it has done its matching,
    you'll need to create a new instance.
    """
    def __init__(self, *matchers):
        self._unmatched = list(matchers)
        self._matched = []

    @classmethod
    def by_equality(cls, *expected_lines):
        return cls(*map(EqualsMatcher, expected_lines))

    @classmethod
    def by_regex(cls, *patterns):
        return cls(*map(RegexMatcher, patterns))

    def match(self, log_line):
        if not self._unmatched:
            raise RuntimeError('Matcher exhausted, no more matchers to use')

        for i, matcher in enumerate(self._unmatched):
            if matcher(log_line):
                self._matched.append(matcher)
                self._unmatched.pop(i)
                break

        if not self._unmatched:
            # All patterns have been matched
            return True

        return False

    def args_str(self):
        matched = [str(m) for m in self._matched]
        unmatched = [str(m) for m in self._unmatched]
        return 'matched=[{}], unmatched=[{}]'.format(
            ', '.join(matched), ', '.join(unmatched))


class EqualsMatcher(LogMatcher):
    """
    Matcher that matches log lines by equality.
    """
    def __init__(self, expected_line):
        self._expected_line = expected_line

    def match(self, log_line):
        return log_line == self._expected_line

    def args_str(self):
        return repr(self._expected_line)


class RegexMatcher(LogMatcher):
    """
    Matcher that matches log lines by regex pattern.
    """
    def __init__(self, pattern):
        self._regex = re.compile(pattern)

    def match(self, log_line):
        return self._regex.search(log_line) is not None

    def args_str(self):
        return repr(self._regex.pattern)


__all__ = ['EqualsMatcher', 'RegexMatcher', 'SequentialLinesMatcher',
           'wait_for_logs_matching']
