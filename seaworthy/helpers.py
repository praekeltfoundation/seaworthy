"""
Classes that track resource creation and removal to ensure that all resources
are namespaced and cleaned up after use.
"""

import logging

import docker
from docker import models

# This is a hack to control our generated documentation. The value of the
# attribute is ignored, only its presence or absence can be detected by the
# apigen machinery.
__apigen_inherited_members__ = None


log = logging.getLogger(__name__)


def fetch_images(client, images):
    """
    Fetch images if they aren't already present.
    """
    return [fetch_image(client, image) for image in images]


def fetch_image(client, name):
    """
    Fetch an image if it isn't already present.

    This works like ``docker pull`` and will pull the tag ``latest`` if no tag
    is specified in the image name.
    """
    try:
        image = client.images.get(name)
    except docker.errors.ImageNotFound:
        name, tag = _parse_image_tag(name)
        tag = 'latest' if tag is None else tag

        log.info("Pulling tag '{}' for image '{}'...".format(tag, name))
        image = client.images.pull(name, tag=tag)

    log.debug("Found image '{}' for tag '{}'".format(image.id, name))
    return image


def _parse_image_tag(name_tag):
    # First get the last part of the name after a '/': this removes the
    # registry which could have a ':' in it
    last_name_part = name_tag.rsplit('/', 1)[-1]

    # Then get the last part after the ':'
    last_parts = last_name_part.rsplit(':', 1)

    if len(last_parts) == 2:
        _, tag = last_parts
        return name_tag[:-(len(tag) + 1)], tag
    else:
        return name_tag, None


def _parse_volume_short_form(short_form):
    parts = short_form.split(':', 1)
    bind = parts[0]
    mode = parts[1] if len(parts) == 2 else 'rw'
    return {'bind': bind, 'mode': mode}


class _HelperBase:
    __collection_type__ = None

    def __init__(self, client, namespace):
        self.collection = self.__collection_type__(client=client)
        self.namespace = namespace

        self._model_name = self.collection.model.__name__.lower()
        self._ids = set()

    def _resource_name(self, name):
        return '{}_{}'.format(self.namespace, name)

    def _get_id_and_model(self, id_or_model):
        """
        Get both the model and ID of an object that could be an ID or a model.

        :param id_or_model:
            The object that could be an ID string or a model object.
        :param model_collection:
            The collection to which the model belongs.
        """
        if isinstance(id_or_model, self.collection.model):
            model = id_or_model
        elif isinstance(id_or_model, str):
            # Assume we have an ID string
            model = self.collection.get(id_or_model)
        else:
            raise TypeError('Unexpected type {}, expected {} or {}'.format(
                type(id_or_model), str, self.collection.model))

        return model.id, model

    def create(self, name, *args, **kwargs):
        """
        Create an instance of this resource type.
        """
        resource_name = self._resource_name(name)
        log.info(
            "Creating {} '{}'...".format(self._model_name, resource_name))
        resource = self.collection.create(*args, name=resource_name, **kwargs)
        self._ids.add(resource.id)
        return resource

    def remove(self, resource, **kwargs):
        """
        Remove an instance of this resource type.
        """
        log.info(
            "Removing {} '{}'...".format(self._model_name, resource.name))
        resource.remove(**kwargs)
        self._ids.remove(resource.id)

    def _teardown(self):
        for resource_id in self._ids.copy():
            # Check if the resource exists before trying to remove it
            try:
                resource = self.collection.get(resource_id)
            except docker.errors.NotFound:
                continue

            log.warning("{} '{}' still existed during teardown".format(
                self._model_name.title(), resource.name))

            self._teardown_remove(resource)

    def _teardown_remove(self, resource):
        # Override in subclass for different removal behaviour on teardown
        self.remove(resource)


class ContainerHelper(_HelperBase):
    """
    .. todo::

        Document this properly.
    """
    __collection_type__ = models.containers.ContainerCollection

    def __init__(self, client, namespace, image_helper, network_helper,
                 volume_helper):
        super().__init__(client, namespace)
        self._image_helper = image_helper
        self._network_helper = network_helper
        self._volume_helper = volume_helper

    def create(self, name, image, fetch_image=False, network=None, volumes={},
               **kwargs):
        """
        Create a new container.

        :param name:
            The name for the container. This will be prefixed with the
            namespace.
        :param image:
            The image tag or image object to create the container from.
        :param network:
            The network to connect the container to. The container will be
            given an alias with the ``name`` parameter. Note that, unlike the
            Docker Python client, this parameter can be a ``Network`` model
            object, and not just a network ID or name.
        :param volumes:
            A mapping of volumes to bind parameters. The keys to this mapping
            can be any of three types of objects:

            - A ``Volume`` model object
            - The name of a volume (str)
            - A path on the host to bind mount into the container (str)

            The bind parameters, i.e. the values in the mapping, can be of
            two types:

            - A full bind specifier (dict), for example
              ``{'bind': '/mnt', 'mode': 'rw'}``
            - A "short-form" bind specifier (str), for example ``/mnt:rw``
        :param fetch_image:
            Whether to attempt to pull the image if it is not found locally.
        :param kwargs:
            Other parameters to create the container with.
        """
        create_kwargs = {
            'detach': True,
        }

        # Convert network & volume models to IDs
        network = self._network_for_container(network, kwargs)
        if network is not None:
            network_id, network = (
                self._network_helper._get_id_and_model(network))
            create_kwargs['network'] = network_id

        if volumes:
            create_kwargs['volumes'] = self._volumes_for_container(volumes)

        create_kwargs.update(kwargs)

        if fetch_image:
            self._image_helper.fetch(image)

        container = super().create(name, image, **create_kwargs)

        if network is not None:
            self._connect_container_network(container, network, aliases=[name])

        return container

    def _network_for_container(self, network, create_kwargs):
        # If a network is specified use that
        if network is not None:
            return network

        # If 'network_mode' is used or networking is disabled, don't handle
        # networking.
        if (create_kwargs.get('network_mode') is not None or
                create_kwargs.get('network_disabled', False)):
            return None

        # Else, use the default network
        return self._network_helper.get_default()

    def _volumes_for_container(self, volumes):
        create_volumes = {}
        for vol, opts in volumes.items():
            try:
                vol_id, _ = self._volume_helper._get_id_and_model(vol)
            except docker.errors.NotFound:
                # Assume this is a bind if we can't find the ID
                vol_id = vol

            if vol_id in create_volumes:
                raise ValueError(
                    "Volume '{}' specified more than once".format(vol_id))

            # Short form of opts
            if isinstance(opts, str):
                opts = _parse_volume_short_form(opts)
            # Else assume long form

            create_volumes[vol_id] = opts
        return create_volumes

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

    def remove(self, container, force=True, volumes=True):
        """
        Remove a container.

        :param container: The container to remove.
        :param force:
            Whether to force the removal of the container, even if it is
            running. Note that this defaults to True, unlike the Docker
            default.
        :param volumes:
            Whether to remove any volumes that were created implicitly with
            this container, i.e. any volumes that were created due to
            ``VOLUME`` directives in the Dockerfile. External volumes that were
            manually created will not be removed. Note that this defaults to
            True, unlike the Docker default (where the equivalent parameter,
            ``v``, defaults to False).
        """
        super().remove(container, force=force, v=volumes)

    def _teardown_remove(self, container):
        self.remove(container, force=True)


class ImageHelper:
    """
    .. todo::

        Document this properly.
    """
    def __init__(self, client):
        self.collection = client.images

    def fetch(self, tag):
        """
        Fetch this image if it isn't already present.
        """
        return fetch_image(self.collection.client, tag)


class NetworkHelper(_HelperBase):
    """
    .. todo::

        Document this properly.
    """
    __collection_type__ = models.networks.NetworkCollection

    def __init__(self, client, namespace):
        super().__init__(client, namespace)
        self._default_network = None

    def _teardown(self):
        # Remove the default network
        if self._default_network is not None:
            self.remove(self._default_network)
            self._default_network = None

        # Remove all other networks
        super()._teardown()

    def get_default(self, create=True):
        """
        Get the default bridge network that containers are connected to if no
        other network options are specified.

        :param create:
            Whether or not to create the network if it doesn't already exist.
        """
        if self._default_network is None and create:
            log.debug("Creating default network...")
            self._default_network = self.create('default', driver='bridge')

        return self._default_network

    def create(self, name, check_duplicate=True, **kwargs):
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
        return super().create(name, check_duplicate=check_duplicate, **kwargs)


class VolumeHelper(_HelperBase):
    """
    .. todo::

        Document this properly.
    """
    __collection_type__ = models.volumes.VolumeCollection

    def create(self, name, **kwargs):
        """
        Create a new volume.

        :param name:
            The name for the volume. This will be prefixed with the namespace.
        :param kwargs:
            Other parameters to create the volume with.
        """
        return super().create(name, **kwargs)


class DockerHelper:
    """
    .. todo::

        Document this properly.
    """

    def __init__(self, namespace='test', client=None):
        self._namespace = namespace
        if client is None:
            client = docker.client.from_env()
        self._client = client

        self.images = ImageHelper(self._client)
        self.networks = NetworkHelper(self._client, namespace)
        self.volumes = VolumeHelper(self._client, namespace)
        self.containers = ContainerHelper(
            self._client, namespace, self.images, self.networks, self.volumes)

    def _helper_for_model(self, model_type):
        """
        Get the helper for a given type of Docker model. For use by resource
        definitions.
        """
        if model_type is models.containers.Container:
            return self.containers
        if model_type is models.images.Image:
            return self.images
        if model_type is models.networks.Network:
            return self.networks
        if model_type is models.volumes.Volume:
            return self.volumes

        raise ValueError('Unknown model type {}'.format(model_type))

    def teardown(self):
        """
        Clean up all resources when we're done with them.
        """
        self.containers._teardown()
        self.networks._teardown()
        self.volumes._teardown()

        # We need to close the underlying APIClient explicitly to avoid
        # ResourceWarnings from unclosed HTTP connections.
        self._client.api.close()
