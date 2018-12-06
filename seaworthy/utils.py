from docker.models.containers import ExecResult


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
