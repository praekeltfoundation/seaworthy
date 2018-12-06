from seaworthy.stream._timeout import stream_timeout


def _last_few_log_lines(container):
    return container.logs(tail=100).decode('utf-8')


def stream_logs(container, timeout=10.0, **logs_kwargs):
    """
    Stream logs from a Docker container within a timeout.

    :param ~docker.models.containers.Container container:
        Container who's log lines to stream.
    :param timeout:
        Timeout value in seconds.
    :param logs_kwargs:
        Additional keyword arguments to pass to ``container.logs()``. For
        example, the ``stdout`` and ``stderr`` boolean arguments can be used to
        determine whether to stream stdout or stderr or both (the default).

    :raises TimeoutError:
        When the timeout value is reached before the logs have completed.
    """
    stream = container.logs(stream=True, **logs_kwargs)
    return stream_timeout(
        stream, timeout, 'Timeout waiting for container logs.')


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
