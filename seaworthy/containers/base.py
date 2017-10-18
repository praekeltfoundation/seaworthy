from seaworthy.logs import (
    RegexMatcher, UnorderedLinesMatcher, stream_logs, stream_with_history,
    wait_for_logs_matching)


def deep_merge(*dicts):
    result = {}
    for d in dicts:
        if not isinstance(d, dict):
            raise Exception('Can only deep_merge dicts, got {}'.format(d))
        for k, v in d.items():
            # Whenever the value is a dict, we deep_merge it. This ensures that
            # (a) we only ever merge dicts with dicts and (b) we always get a
            # deep(ish) copy of the dicts and are thus safe from accidental
            # mutations to shared state.
            if isinstance(v, dict):
                v = deep_merge(result.get(k, {}), v)
            result[k] = v
    return result


class ContainerBase:
    WAIT_TIMEOUT = 10.0

    def __init__(self, name, image, wait_patterns=None, wait_timeout=None,
                 create_kwargs=None):
        """
        :param name:
            The name for the container. The actual name of the container is
            namespaced by DockerHelper. This name will be used as a network
            alias for the container.
        :param image: image tag to use
        :param list wait_patterns:
            Regex patterns to use when checking that the container has started
            successfully.
        :param wait_timeout:
            Number of seconds to wait for the ``wait_patterns``. Defaults to
            ``self.WAIT_TIMEOUT``.
        """
        self.name = name
        self.image = image
        if wait_patterns:
            self.wait_matchers = [RegexMatcher(p) for p in wait_patterns]
        else:
            self.wait_matchers = None
        if wait_timeout is not None:
            self.wait_timeout = wait_timeout
        else:
            self.wait_timeout = self.WAIT_TIMEOUT

        self._create_kwargs = {} if create_kwargs is None else create_kwargs

        self._container = None

    def create_and_start(self, docker_helper, pull=True, kwargs=None):
        """
        Create the container and start it, waiting for the expected log lines.

        :param pull:
            Whether or not to attempt to pull the image if the image tag is not
            known.
        """
        if self._container is not None:
            raise RuntimeError('Container already created.')

        if pull:
            docker_helper.pull_image_if_not_found(self.image)

        kwargs = {} if kwargs is None else kwargs
        kwargs = self.merge_kwargs(self._create_kwargs, kwargs)

        self._container = docker_helper.create_container(
            self.name, self.image, **kwargs)
        docker_helper.start_container(self._container)

        self.wait_for_start()

    def wait_for_start(self):
        """
        Wait for the container to start.

        By default this will wait for the log lines matching the patterns
        passed in the ``wait_patterns`` parameter of the constructor using an
        UnorderedLinesMatcher. For more advanced checks for container startup,
        this method should be overridden.
        """
        if self.wait_matchers:
            matcher = UnorderedLinesMatcher(*self.wait_matchers)
            self.wait_for_logs_matching(matcher, timeout=self.wait_timeout)

    def stop_and_remove(self, docker_helper):
        """ Stop the container and remove it. """
        docker_helper.stop_and_remove_container(self.inner())
        self._container = None

    def inner(self):
        """
        :returns: the underlying Docker container object
        :rtype: docker.models.containers.Container
        """
        if self._container is None:
            raise RuntimeError('Container not created yet.')
        return self._container

    def merge_kwargs(self, default_kwargs, kwargs):
        """
        Override this method to merge kwargs differently.
        """
        return deep_merge(default_kwargs, kwargs)

    def clean(self):
        """
        This method should "clean" the container so that it is in the same
        state as it was when it was started.
        """
        raise NotImplementedError()

    @property
    def ports(self):
        """
        The ports (exposed and published) of the container.
        """
        return self.inner().attrs['NetworkSettings']['Ports']

    def _host_port(self, port_spec, index):
        if port_spec not in self.ports:
            raise ValueError("Port '{}' is not exposed".format(port_spec))

        mappings = self.ports[port_spec]
        if mappings is None:
            raise ValueError(
                "Port '{}' is not published to the host".format(port_spec))

        mapping = mappings[index]
        return mapping['HostIp'], mapping['HostPort']

    def get_host_port(self, container_port, proto='tcp', index=0):
        """
        :param container_port: The container port.
        :param proto: The protocol ('tcp' or 'udp').
        :param index: The index of the mapping entry to return.
        :returns: A tuple of the interface IP and port on the host.
        """
        port_spec = '{}/{}'.format(container_port, proto)
        return self._host_port(port_spec, index)

    def get_first_host_port(self):
        """
        Get the first mapping of the first (lowest) container port that has a
        mapping. Useful when a container publishes only one port.

        Note that unlike the Docker API, which sorts ports lexicographically
        (e.g. ``90/tcp`` > ``8000/tcp``), we sort ports numerically so that the
        lowest port is always chosen.
        """
        mapped_ports = {p: m for p, m in self.ports.items() if m is not None}
        if not mapped_ports:
            raise RuntimeError('Container has no published ports')

        def sort_key(port_string):
            port, proto = port_string.split('/', 1)
            return int(port), proto
        firt_port_spec = sorted(mapped_ports.keys(), key=sort_key)[0]

        return self._host_port(firt_port_spec, 0)

    def get_logs(self, stdout=True, stderr=True, timestamps=False, tail='all',
                 since=None):
        """
        Get container logs.

        This method does not support streaming, use :meth:`stream_logs` for
        that.
        """
        return self.inner().logs(
            stdout=stdout, stderr=stderr, timestamps=timestamps, tail=tail,
            since=since)

    def stream_logs(self, stdout=True, stderr=True, old_logs=False,
                    timeout=10.0):
        """
        Stream container output.
        """
        stream_func = stream_with_history if old_logs else stream_logs
        return stream_func(
                self.inner(), stdout=stdout, stderr=stderr, timeout=timeout)

    def wait_for_logs_matching(self, matcher, timeout=10, encoding='utf-8',
                               **logs_kwargs):
        """
        Wait for logs matching the given matcher.
        """
        wait_for_logs_matching(
            self.inner(), matcher, timeout=timeout, encoding=encoding,
            **logs_kwargs)
