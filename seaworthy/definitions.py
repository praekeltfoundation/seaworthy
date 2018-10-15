"""
Wrappers over Docker resource types to aid in setup/teardown of and interaction
with Docker resources.
"""

import functools

from docker import models

from seaworthy.helpers import DockerHelper
from seaworthy.stream.logs import stream_logs, wait_for_logs_matching
from seaworthy.stream.matchers import RegexMatcher, UnorderedMatcher


# This is a hack to control our generated documentation. The value of the
# attribute is ignored, only its presence or absence can be detected by the
# apigen machinery.
__apigen_inherited_members__ = None


def deep_merge(*dicts):
    """
    Recursively merge all input dicts into a single dict.
    """
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


class _DefinitionBase:
    __model_type__ = None

    def __init__(self, name, create_kwargs=None, helper=None):
        self.name = name

        self._create_args = ()
        self._create_kwargs = {} if create_kwargs is None else create_kwargs

        self._helper = None
        self.set_helper(helper)

        self._inner = None

    def create(self, **kwargs):
        """
        Create an instance of this resource definition.

        Only one instance may exist at any given time.
        """
        if self.created:
            raise RuntimeError(
                '{} already created.'.format(self.__model_type__.__name__))

        kwargs = self.merge_kwargs(self._create_kwargs, kwargs)

        self._inner = self.helper.create(
            self.name, *self._create_args, **kwargs)

    def remove(self, **kwargs):
        """
        Remove an instance of this resource definition.
        """
        self.helper.remove(self.inner(), **kwargs)
        self._inner = None

    def setup(self, helper=None, **create_kwargs):
        """
        Setup this resource so that is ready to be used in a test. If the
        resource has already been created, this call does nothing.

        For most resources, this just involves creating the resource in Docker.

        :param helper:
            The resource helper to use, if one was not provided when this
            resource definition was created.
        :param **create_kwargs: Keyword arguments passed to :meth:`.create`.

        :returns:
            This definition instance. Useful for creating and setting up a
            resource in a single step::

                volume = VolumeDefinition('volly').setup(helper=docker_helper)
        """
        if self.created:
            return

        self.set_helper(helper)
        self.create(**create_kwargs)
        return self

    def teardown(self):
        """
        Teardown this resource so that it no longer exists in Docker. If the
        resource has already been removed, this call does nothing.

        For most resources, this just involves removing the resource in Docker.
        """
        if not self.created:
            return

        self.remove()

    def __enter__(self):
        return self.setup()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.teardown()

    @property
    def helper(self):
        if self._helper is None:
            raise RuntimeError('No helper set.')
        return self._helper

    def set_helper(self, helper):
        """
        .. todo::

            Document this.
        """
        # We don't want to "unset" in this method.
        if helper is None:
            return

        # Get the right kind of helper if given a DockerHelper
        if isinstance(helper, DockerHelper):
            helper = helper._helper_for_model(self.__model_type__)

        # We already have this one.
        if helper is self._helper:
            return
        if self._helper is None:
            self._helper = helper
        else:
            raise RuntimeError('Cannot replace existing helper.')

    def as_fixture(self, name=None):
        """
        A decorator to inject this container into a function as a test fixture.
        """
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

    def inner(self):
        """
        :returns: the underlying Docker model object
        """
        if not self.created:
            raise RuntimeError(
                '{} not created yet.'.format(self.__model_type__.__name__))
        return self._inner

    @property
    def created(self):
        return self._inner is not None

    def base_kwargs(self):
        """
        Override this method to provide dynamically generated base kwargs for
        the resource.
        """
        return {}

    def merge_kwargs(self, default_kwargs, kwargs):
        """
        Override this method to merge kwargs differently.
        """
        return deep_merge(self.base_kwargs(), default_kwargs, kwargs)


class ContainerDefinition(_DefinitionBase):
    """
    This is the base class for container definitions. Instances (and instances
    of subclasses) are intended to be used both as test fixtures and as
    convenient objects for operating on containers being tested.

    .. todo::

        Document this properly.

    A container object may be used as a context manager to ensure proper setup
    and teardown of the container around the code that uses it::

        with ContainerDefinition('my_container', IMAGE, helper=ch) as c:
            assert c.status() == 'running'

    (Note that this only works if the container has a helper set and does not
    have a container created.)
    """

    __model_type__ = models.containers.Container
    WAIT_TIMEOUT = 10.0

    def __init__(self, name, image, wait_patterns=None, wait_timeout=None,
                 create_kwargs=None, helper=None):
        """
        :param name:
            The name for the container. The actual name of the container is
            namespaced by ContainerHelper. This name will be used as a network
            alias for the container.
        :param image: image tag to use
        :param list wait_patterns:
            Regex patterns to use when checking that the container has started
            successfully.
        :param wait_timeout:
            Number of seconds to wait for the ``wait_patterns``. Defaults to
            ``self.WAIT_TIMEOUT``.
        :param dict create_kwargs:
            Other kwargs to use when creating the container.
        :param seaworthy.helper.ContainerHelper helper:
            A ContainerHelper instance used to create containers.
        """
        super().__init__(name, create_kwargs=create_kwargs, helper=helper)

        self._create_args = (image,)
        if wait_patterns:
            self.wait_matchers = [RegexMatcher(p) for p in wait_patterns]
        else:
            self.wait_matchers = None
        if wait_timeout is not None:
            self.wait_timeout = wait_timeout
        else:
            self.wait_timeout = self.WAIT_TIMEOUT

        self._http_clients = []

    def setup(self, helper=None, **run_kwargs):
        """
        Creates the container, starts it, and waits for it to completely start.

        :param helper:
            The resource helper to use, if one was not provided when this
            container definition was created.
        :param **run_kwargs: Keyword arguments passed to :meth:`.run`.

        :returns:
            This container definition instance. Useful for creating and setting
            up a container in a single step::

                con = ContainerDefinition('conny', 'nginx').setup(helper=dh)
        """
        if self.created:
            return

        self.set_helper(helper)
        self.run(**run_kwargs)
        self.wait_for_start()
        return self

    def teardown(self):
        """
        Stop and remove the container if it exists.
        """
        while self._http_clients:
            self._http_clients.pop().close()
        if self.created:
            self.halt()

    def status(self):
        """
        Get the container's current status from Docker.

        If the container does not exist (before creation and after removal),
        the status is ``None``.
        """
        if not self.created:
            return None
        self.inner().reload()
        return self.inner().status

    def start(self):
        """
        Start the container. The container must have been created.
        """
        self.inner().start()
        self.inner().reload()

    def stop(self, timeout=5):
        """
        Stop the container. The container must have been created.

        :param timeout:
            Timeout in seconds to wait for the container to stop before sending
            a ``SIGKILL``. Default: 5 (half the Docker default)
        """
        self.inner().stop(timeout=timeout)
        self.inner().reload()

    def run(self, fetch_image=True, **kwargs):
        """
        Create the container and start it. Similar to ``docker run``.

        :param fetch_image:
            Whether to try pull the image if it's not found. The behaviour here
            is similar to ``docker run`` and this parameter defaults to
            ``True``.
        :param **kwargs: Keyword arguments passed to :meth:`.create`.
        """
        self.create(fetch_image=fetch_image, **kwargs)
        self.start()

    def wait_for_start(self):
        """
        Wait for the container to start.

        By default this will wait for the log lines matching the patterns
        passed in the ``wait_patterns`` parameter of the constructor using an
        UnorderedMatcher. For more advanced checks for container startup, this
        method should be overridden.
        """
        if self.wait_matchers:
            matcher = UnorderedMatcher(*self.wait_matchers)
            self.wait_for_logs_matching(matcher, timeout=self.wait_timeout)

    def halt(self, stop_timeout=5):
        """
        Stop the container and remove it. The opposite of :meth:`run`.
        """
        self.stop(timeout=stop_timeout)
        self.remove()

    def clean(self):
        """
        This method should "clean" the container so that it is in the same
        state as it was when it was started. It is up to the implementer of
        this method to decide how the container should be cleaned. See
        :func:`~seaworthy.pytest.fixtures.clean_container_fixtures` for how
        this can be used with pytest fixtures.
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

    def stream_logs(self, stdout=True, stderr=True, tail='all', timeout=10.0):
        """
        Stream container output.
        """
        return stream_logs(
            self.inner(), stdout=stdout, stderr=stderr, tail=tail,
            timeout=timeout)

    def wait_for_logs_matching(self, matcher, timeout=10, encoding='utf-8',
                               **logs_kwargs):
        """
        Wait for logs matching the given matcher.
        """
        wait_for_logs_matching(
            self.inner(), matcher, timeout=timeout, encoding=encoding,
            **logs_kwargs)

    def http_client(self, port=None):
        """
        Construct an HTTP client for this container.
        """
        # Local import to avoid potential circularity.
        from seaworthy.client import ContainerHttpClient
        client = ContainerHttpClient.for_container(self, container_port=port)
        self._http_clients.append(client)
        return client


class NetworkDefinition(_DefinitionBase):
    """
    This is the base class for network definitions.

    .. todo::

        Document this properly.
    """
    __model_type__ = models.networks.Network


class VolumeDefinition(_DefinitionBase):
    """
    This is the base class for volume definitions.

    The following is an example of how ``VolumeDefinition`` can be used to
    attach volumes to a container::

        from seaworthy.definitions import ContainerDefinition

        class DjangoContainer(ContainerDefinition):
            IMAGE = "seaworthy-demo:django"
            WAIT_PATTERNS = (r"Booting worker",)

            def __init__(self, name, socket_volume, static_volume, db_url):
                super().__init__(name, self.IMAGE, self.WAIT_PATTERNS)
                self.socket_volume = socket_volume
                self.static_volume = static_volume
                self.db_url = db_url

            def base_kwargs(self):
                return {
                    "volumes": {
                        self.socket_volume.inner(): "/var/run/gunicorn",
                        self.static_volume.inner(): "/app/static:ro",
                    },
                    "environment": {"DATABASE_URL": self.db_url}
                }

        # Create definition instances
        socket_volume = VolumeDefinition("socket")
        static_volume = VolumeDefinition("static")
        django_container = DjangoContainer(
            "django", socket_volume, static_volume,
            postgresql_container.database_url())

        # Create pytest fixtures
        socket_volume_fixture = socket_volume.pytest_fixture("socket_volume")
        static_volume_fixture = static_volume.pytest_fixture("static_volume")
        django_fixture = django_container.pytest_fixture(
            "django_container",
            dependencies=[
                "socket_volume", "static_volume", "postgresql_container"])

    This example is explained in the `introductory blog post`_ and
    `demo repository`_.

    .. todo::

        Document this properly.

    .. _`introductory blog post`:
        https://medium.com/mobileforgood/patterns-for-continuous-integration-with-docker-on-travis-ci-ba7e3a5ca2aa
    .. _`demo repository`:
        https://github.com/JayH5/seaworthy-demo
    """
    __model_type__ = models.volumes.Volume
