import logging

import docker

log = logging.getLogger(__name__)


def fetch_images(client, images):
    """
    Fetch images if they aren't already present.
    """
    return [fetch_image(client, image) for image in images]


def fetch_image(client, name):
    """
    Fetch an image if it isn't already present.
    """
    try:
        image = client.images.get(name)
    except docker.errors.ImageNotFound:
        log.info("Pulling tag '{}'...".format(name))
        image = client.images.pull(name)

    log.debug("Found image '{}' for tag '{}'".format(image.id, name))
    return image


class DockerHelper:
    def __init__(self, namespace='test'):
        self._namespace = namespace

        self._client = None
        self._container_ids = None
        self._default_network = None

    def _resource_name(self, name):
        return '{}_{}'.format(self._namespace, name)

    def setup(self):
        self._client = docker.client.from_env()
        self._container_ids = set()

    def teardown(self):
        if self._client is None:
            return

        self._teardown_containers()

        # Remove the default network
        if self._default_network is not None:
            self._default_network.remove()
            self._default_network = None

        # We need to close the underlying APIClient explicitly to avoid
        # ResourceWarnings from unclosed HTTP connections.
        self._client.api.close()
        self._client = None

    def _teardown_containers(self):
        # Remove all containers
        for container_id in self._container_ids.copy():
            # Check if the container exists before trying to remove it
            try:
                container = self._client.containers.get(container_id)
            except docker.errors.NotFound:
                continue

            log.warning("Container '{}' still existed during teardown".format(
                container.name))

            if container.status == 'running':
                self.stop_container(container)
            self.remove_container(container)
        self._container_ids = None

    def get_default_network(self, create=True):
        """
        Get the default bridge network that containers are connected to if no
        other network options are specified.

        :param create:
            Whether or not to create the network if it doesn't already exist.
        """
        if self._default_network is None and create:
            # Docker allows the creation of multiple networks with the same
            # name (unlike containers). This seems to cause problems sometimes
            # with container networking for some reason (?).
            network_name = self._resource_name('default')
            log.info("Creating default network '{}'...".format(network_name))

            if self._client.networks.list(names=[network_name]):
                raise RuntimeError(
                    "A network with the name '{}' already exists".format(
                        network_name))

            self._default_network = (
                self._client.networks.create(network_name, driver='bridge'))

        return self._default_network

    def create_container(self, name, image, **kwargs):
        container_name = self._resource_name(name)
        log.info("Creating container '{}'...".format(container_name))

        network = self._get_container_network(**kwargs)
        network_id = network.id if network is not None else None

        container = self._client.containers.create(
            image, name=container_name, detach=True, network=network_id,
            **kwargs)

        if network is not None:
            self._connect_container_network(container, network, aliases=[name])

        # Keep a reference to created containers to make sure they are cleaned
        # up
        self._container_ids.add(container.id)

        return container

    def _get_container_network(self, **create_kwargs):
        # If a network is specified use that
        network = create_kwargs.get('network')
        if network is not None:
            return network

        # If 'network_mode' is used or networking is disabled, don't handle
        # networking.
        if (create_kwargs.get('network_mode') is not None or
                create_kwargs.get('network_disabled', False)):
            return None

        # Else, use the default network
        return self.get_default_network()

    def _connect_container_network(self, container, network, **connect_kwargs):
        # FIXME: Hack to make sure the container has the right network aliases.
        # Only the low-level Docker client API allows us to specify endpoint
        # aliases at container creation time:
        # https://docker-py.readthedocs.io/en/stable/api.html#docker.api.container.ContainerApiMixin.create_container
        # If we don't specify a network when the container is created then the
        # default bridge network is attached which we don't want, so we
        # reattach our custom network as that allows specifying aliases.
        network.disconnect(container)
        network.connect(container, **connect_kwargs)
        # Reload the container data to get the new network setup
        container.reload()

    def container_status(self, container):
        container.reload()
        log.debug("Container '{}' has status '{}'".format(
            container.name, container.status))
        return container.status

    def start_container(self, container):
        log.info("Starting container '{}'...".format(container.name))
        container.start()
        # If the container is short-lived, it may have finished and exited
        # before we check its status.
        assert self.container_status(container) in ['running', 'exited']

    def stop_container(self, container, timeout=5):
        log.info("Stopping container '{}'...".format(container.name))
        container.stop(timeout=timeout)
        assert self.container_status(container) != 'running'

    def remove_container(self, container, force=True):
        log.info("Removing container '{}'...".format(container.name))
        container.remove(force=force)

        self._container_ids.remove(container.id)

    def stop_and_remove_container(
            self, container, stop_timeout=5, remove_force=True):
        self.stop_container(container, timeout=stop_timeout)
        self.remove_container(container, force=remove_force)

    def pull_image_if_not_found(self, image):
        return fetch_image(self._client, image)
