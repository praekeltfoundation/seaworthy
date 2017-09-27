from seaworthy.logs import (
    RegexMatcher, SequentialLinesMatcher, stream_logs, stream_with_history,
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
    def __init__(self, name, image, wait_patterns=None, create_kwargs=None):
        """
        :param name:
            The name for the container. The actual name of the container is
            namespaced by DockerHelper. This name will be used as a network
            alias for the container.
        :param image: image tag to use
        :param list wait_patterns:
            Regex patterns to use when checking that the container has started
            successfully.
        """
        self.name = name
        self.image = image
        if wait_patterns:
            self.wait_matchers = [RegexMatcher(p) for p in wait_patterns]
        else:
            self.wait_matchers = None

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

        self.wait_for_start(docker_helper, self._container)

    def wait_for_start(self, docker_helper, container):
        """
        Wait for the container to start.

        By default this will wait for the log lines matching the patterns
        passed in the ``wait_patterns`` parameter of the constructor. For more
        advanced checks for container startup, this method should be
        overridden.

        :param DockerHelper docker_helper:
        :param docker.models.containers.Container container:
        """
        if self.wait_matchers:
            self.wait_for_logs_matching(
                SequentialLinesMatcher(*self.wait_matchers))

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

    def get_host_port(self, port_spec, index=0):
        """
        :param port_spec: A container port mapping specifier.
        :param index: The index of the mapping entry to return.
        :returns: The host port the container is mapped to.
        """
        # FIXME: The mapping entries are not necessarily in a sensible order.
        ports = self.inner().attrs['NetworkSettings']['Ports']
        return ports[port_spec][index]['HostPort']

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
