def resource_name(name, namespace='test'):
    return '{}_{}'.format(namespace, name)


def output_lines(raw_output, encoding='utf-8'):
    return raw_output.decode(encoding).splitlines()
