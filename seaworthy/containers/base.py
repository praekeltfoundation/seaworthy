import functools

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
    """
    This is the base class for container definitions. Instances (and instances
    of subclasses) are intended to be used both as test fixtures and as
    convenient objects for operating on containers being tested.

    TODO: Document this properly.
     * basic usage
     * context manager
    """

    WAIT_TIMEOUT = 10.0

    def __init__(self, name, image, wait_patterns=None, wait_timeout=None,
                 create_kwargs=None, docker_helper=None):
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

        self._docker_helper = docker_helper
        self._container = None

    @property
    def docker_helper(self):
        if self._docker_helper is None:
            raise RuntimeError('No docker_helper set.')
        return self._docker_helper

    def __enter__(self):
        self.create_and_start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._teardown()

    def _teardown(self):
        """
        Stop and remove the container if it exists.
        """
        if self._container is not None:
            self.stop_and_remove()

    def as_fixture(self, name=None):
        if name is None:
            name = self.name

        def deco(f):
            @functools.wraps(f)
            def wrapper(*args, **kw):
                with self:
                    kw[name] = self
                    return f(*args, **kw)
            return wrapper
        return deco

    def set_docker_helper(self, docker_helper):
        if docker_helper is None:  # We don't want to "unset" in this method.
            return
        if docker_helper is self._docker_helper:  # We already have this one.
            return
        if self._docker_helper is None:
            self._docker_helper = docker_helper
        else:
            raise RuntimeError('Cannot replace existing docker_helper.')

    def status(self):
        """
        Get the container's status. If the container does not exist (before
        creation and after removal), the status is ``None``.
        """
        if self._container is None:
            return None
        return self.docker_helper.containers.status(self.inner())

    def create_and_start(self, docker_helper=None, pull=True, kwargs=None):
        """
        Create the container and start it, waiting for the expected log lines.

        :param pull:
            Whether or not to attempt to pull the image if the image tag is not
            known.
        """
        self.set_docker_helper(docker_helper)
        if self._container is not None:
            raise RuntimeError('Container already created.')

        if pull:
            self.docker_helper.pull_image_if_not_found(self.image)

        kwargs = {} if kwargs is None else kwargs
        kwargs = self.merge_kwargs(self._create_kwargs, kwargs)

        self._container = self.docker_helper.containers.create(
            self.name, self.image, **kwargs)
        self.docker_helper.containers.start(self._container)

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

    def stop_and_remove(self):
        """ Stop the container and remove it. """
        self.docker_helper.containers.stop_and_remove(self.inner())
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
