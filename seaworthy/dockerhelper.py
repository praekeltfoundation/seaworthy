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


def _get_id(resource):
    """
    Get the ID of the given resource if it is a Docker Model object. If the
    given object is a string, assume it is the ID. Else, return None.
    """
    if isinstance(resource, docker.models.resource.Model):
        return resource.id
    if isinstance(resource, str):
        return resource
    return None


class DockerHelper:
    def __init__(self, namespace='test'):
        self._namespace = namespace

        self._client = None
        self._container_ids = None
        self._network_ids = None
        self._volume_ids = None
        self._default_network = None

    def _resource_name(self, name):
        return '{}_{}'.format(self._namespace, name)

    def setup(self):
        self._client = docker.client.from_env()
        self._container_ids = set()
        self._network_ids = set()
        self._volume_ids = set()

    def teardown(self):
        if self._client is None:
            return

        self._teardown_containers()
        self._teardown_networks()
        self._teardown_volumes()

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

    def _teardown_networks(self):
        # Remove the default network
        if self._default_network is not None:
            self._default_network.remove()
            self._default_network = None

        # Remove all other networks
        for network_id in self._network_ids.copy():
            # Check if the network exists before trying to remove it
            try:
                network = self._client.networks.get(network_id)
            except docker.errors.NotFound:
                continue

            log.warning("Network '{}' still existed during teardown".format(
                network.name))

            self.remove_network(network)
        self._network_ids = None

    def _teardown_volumes(self):
        # Remove all volumes
        for volume_id in self._volume_ids.copy():
            # Check if the volume exists before trying to remove it
            try:
                volume = self._client.volumes.get(volume_id)
            except docker.errors.NotFound:
                continue

            log.warning("Volume '{}' still existed during teardown".format(
                volume.name))

            self.remove_volume(volume)
        self._volume_ids = None

    def get_default_network(self, create=True):
        """
        Get the default bridge network that containers are connected to if no
        other network options are specified.

        :param create:
            Whether or not to create the network if it doesn't already exist.
        """
        if self._default_network is None and create:
            log.debug("Creating default network...")
            self._default_network = self.create_network(
                'default', driver='bridge')

        return self._default_network

    def create_container(
            self, name, image, network=None, volumes={}, **kwargs):
        """
        Create a new container.

        :param name:
            The name for the container. This will be prefixed with the
            namespace.
        :param image:
            The image tag or image object to create the container from.
        :param docker.models.networks.Network network:
            The network to connect the container to. The container will be
            given an alias with the ``name`` parameter. Note that, unlike the
            Docker Python client, this parameter should be a ``Network`` model
            object, and not just a network ID.
        :param volumes:
            A mapping of Volume model objects or volume IDs to bind parameters.
        :param kwargs:
            Other parameters to create the container with.
        """
        container_name = self._resource_name(name)
        log.info("Creating container '{}'...".format(container_name))

        network = self._get_container_network(network, kwargs)
        volumes = self._get_container_volumes(volumes, kwargs)

        container = self._client.containers.create(
            image, name=container_name, detach=True, network=_get_id(network),
            volumes=volumes, **kwargs)

        if network is not None:
            self._connect_container_network(container, network, aliases=[name])

        # Keep a reference to created containers to make sure they are cleaned
        # up
        self._container_ids.add(container.id)

        return container

    def _get_container_network(self, network, create_kwargs):
        # If a network is specified use that
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
        # We could also reload the network data to update the containers that
        # are connected to it but that listing doesn't include containers that
        # have been created and connected but not yet started. :-/

    def _get_container_volumes(self, volumes, create_kwargs):
        # If there are volumes, map the Volume models to IDs
        if volumes:
            return {_get_id(vol): opts for vol, opts in volumes.items()}
        return None

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

    def create_network(self, name, check_duplicate=True, **kwargs):
        """
        Create a new network.

        :param name:
            The name for the network. This will be prefixed with the namespace.
        :param check_duplicate:
            Whether or not to check for networks with the same name. Docker
            allows the creation of multiple networks with the same name (unlike
            containers). This seems to cause problems sometimes for some reason
            (?). The Docker Python client _claims_ (as of 2.5.1) that
            ``check_duplicate`` defaults to True but it actually doesn't. We
            default it to True ourselves here.
        :param kwargs:
            Other parameters to create the network with.
        """
        network_name = self._resource_name(name)
        log.info("Creating network '{}'...".format(network_name))

        network = self._client.networks.create(
            name=network_name, check_duplicate=check_duplicate, **kwargs)
        self._network_ids.add(network.id)
        return network

    def remove_network(self, network):
        log.info("Removing network '{}'...".format(network.name))
        network.remove()

        self._network_ids.remove(network.id)

    def create_volume(self, name, **kwargs):
        """
        Create a new volume.

        :param name:
            The name for the volume. This will be prefixed with the namespace.
        :param kwargs:
            Other parameters to create the volume with.
        """
        volume_name = self._resource_name(name)
        log.info("Creating volume '{}'...".format(volume_name))

        volume = self._client.volumes.create(name=volume_name, **kwargs)
        self._volume_ids.add(volume.id)
        return volume

    def remove_volume(self, volume, force=False):
        log.info("Removing volume '{}'...".format(volume.name))
        volume.remove(force=force)

        self._volume_ids.remove(volume.id)
