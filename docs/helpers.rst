Resource helpers
================
One of the core concepts of Seaworthy is the concept of a resource helper.
These are wrappers around the resource models provided by the `Docker SDK for
Python`_. There is a helper class for each of the basic Docker resource types:

- :class:`~seaworthy.helper.ImageHelper` manages
  :class:`docker.models.images.Image` resources
- :class:`~seaworthy.helper.NetworkHelper` manages
  :class:`docker.models.networks.Network` resources
- :class:`~seaworthy.helper.VolumeHelper` manages
  :class:`docker.models.volumes.Volume` resources
- :class:`~seaworthy.helper.ContainerHelper` manages
  :class:`docker.models.containers.Container` resources

These helpers all provide two main functions:

- Namespacing of resources: by prefixing resource names, the resources are
  isolated from other Docker resources already present on the system.
- Teardown (cleanup) of resources: when the tests end, the networks, volumes,
  and containers used in those tests are removed.

In addition, some of the behaviour around resource creation and removal is
changed from the Docker defaults to be a better fit for a testing environment.

Accessing the various helpers is most easily done via the
:class:`~seaworthy.helper.DockerHelper`::

    from seaworthy.helper import DockerHelper


    # Create a DockerHelper with the default namespace, 'test'
    docker_helper = DockerHelper()

    # Create a network using the NetworkHelper
    network = docker_helper.networks.create('private')

    # Create a volume using the VolumeHelper
    volume = docker_helper.volumes.create('shared')

    # Fetch (pull) an image using the ImageHelper
    image = docker_helper.images.fetch('busybox')

    # Create a container using the ContainerHelper
    container = docker_helper.containers.create(
        'conny', image, network=network, volumes={volume: '/vol'})

The DockerHelper can be configured with a custom Docker API client. The default
client can be configured using environment variables. See
:meth:`docker.client.from_env`.


.. _`Docker SDK for Python`: https://docker-py.readthedocs.io/
