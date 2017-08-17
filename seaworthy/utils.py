import re

from stopit import SignalTimeout, TimeoutException


def resource_name(name, namespace='test'):
    return '{}_{}'.format(namespace, name)


def _last_few_log_lines(container, max_lines=100):
    logs = container.logs(tail=max_lines).decode('utf-8')
    return '\nLast few log lines:\n{}'.format(logs)


def wait_for_log_line(container, pattern, timeout=10):
    try:
        # stopit.ThreadingTimeout doesn't seem to work but a Unix-only
        # solution should be fine for now :-/
        with SignalTimeout(timeout):
            for line in container.logs(stream=True):
                # Drop the trailing newline
                line = line.decode('utf-8').rstrip()
                if re.search(pattern, line):
                    return line
    except TimeoutException:
        # In Python 3 we have TimeoutError
        raise TimeoutError('Timeout waiting for log pattern {!r}.{}'.format(
            pattern, _last_few_log_lines(container)))

    raise RuntimeError('Log pattern {!r} not found in logs.{}'.format(
        pattern, _last_few_log_lines(container)))


def output_lines(raw_output, encoding='utf-8'):
    return raw_output.decode(encoding).splitlines()
