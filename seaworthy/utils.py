from docker.models.containers import ExecResult


def output_lines(output, encoding='utf-8', error_exc=None):
    """
    Convert bytestring container output or the result of a container exec
    command into a sequence of unicode lines.

    :param output:
        Container output bytes or an
        :class:`docker.models.containers.ExecResult` instance.
    :param encoding:
        The encoding to use when converting bytes to unicode
        (default ``utf-8``).
    :param error_exc:
        Optional exception to raise if ``output`` is an ``ExecResult`` with a
        nonzero exit code.

    :returns: list[str]

    """
    if isinstance(output, ExecResult):
        exit_code, output = output
        if exit_code != 0 and error_exc is not None:
            raise error_exc(output.decode(encoding))

    return output.decode(encoding).splitlines()
