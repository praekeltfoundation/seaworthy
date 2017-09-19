from seaworthy.logs import (
    RegexMatcher, SequentialLinesMatcher, wait_for_logs_matching)


class ContainerBase:
    def __init__(self, name, image, wait_patterns=None):
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

        self._container = None

    def create_and_start(self, docker_helper, pull=True):
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

        self._container = docker_helper.create_container(
            self.name, self.image, **self.create_kwargs())
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
            wait_for_logs_matching(
                self._container, SequentialLinesMatcher(*self.wait_matchers))

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

    def create_kwargs(self):
        """
        :returns:
            any extra keyword arguments to pass to
            ~DockerHelper.create_container
        :rtype: dict
        """
        return {}

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
