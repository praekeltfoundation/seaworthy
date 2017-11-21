Resource definitions & helpers
==============================
Two important abstractions in Seaworthy are resource *definitions* and
*helpers*. These provide test-oriented interfaces to all of the basic
(non-Swarm) Docker resource types.

Definitions
-----------
Resource definitions provide three main functions:

- Make it possible to *define* resources before those resources are actually
  created in Docker. This is important for creating test fixtures—if we can
  define everything about a resource before it is created, then we can create
  the resource when it is needed as a fixture for a test.
- Simplify the setup and teardown of resources before and after tests. For
  example, :class:`~seaworthy.definitions.ContainerDefinition` can be used to
  check that a container has produced certain log lines before it is used in a
  test.
- Provide useful functionality to interact with and introspect resources. For
  example, the :meth:`~seaworthy.definitions.ContainerDefinition.http_client`
  method can be used to get a simple HTTP client to make requests against a
  container.

Resource defintions can either be instantiated directly or subclassed to
provide more specialised functionality.

For a simple volume, one could create an instance of
:class:`~seaworthy.definitions.VolumeDefinition`::

    from seaworthy.definitions import VolumeDefinition
    from seaworthy.helpers import DockerHelper


    docker_helper = DockerHelper()
    volume = VolumeDefinition('persist', helper=docker_helper)


Using definitions in tests
^^^^^^^^^^^^^^^^^^^^^^^^^^
Definitions can be used as fixtures for tests in a number of different ways.

As a context manager::

    with VolumeDefinition('files', helper=docker_helper) as volume:
        assert volume.created

    assert not volume.created

With the ``as_fixture`` decorator::

    network = NetworkDefinition('lan_network', helper=docker_helper)

    @network.as_fixture()
    def test_network(lan_network):
        assert lan_network.created

When using pytest, it's easy to create a fixture::

    from seaworthy.pytest.fixtures import resource_fixture


    container = ContainerDefinition('nginx', 'nginx:alpine')
    fixture = container.pytest_fixture('nginx_container')

    def test_nginx(nginx_container):
        assert nginx_container.created

You can also use classic xunit-style setup/teardown::

    import unittest


    class EchoContainerTest(unittest.TestCase):
        def setUp(self):
            self.helper = DockerHelper()
            self.container = ContainerDefinition('echo', 'jmalloc/echo-server')
            self.container.setup(helper=self.helper)
            self.addCleanup(self.container.teardown)

        def test_container(self):
            self.assertTrue(self.container.created)


Relationship to helpers
^^^^^^^^^^^^^^^^^^^^^^^
Every resource definition instance needs to have a "helper" set before it is
possible to actually create the Docker resource that the instance defines.
Resource helpers are described in more detail later in this section, but for
now, know that a helper needs to be provided to the definition in one of three
ways:

1. Using the ``helper`` keyword argument in the constuctor::

    helper = DockerHelper()
    network = NetworkDefinition('net01', helper=helper)
    network.setup()

2. Using the ``helper`` keyword argument in the ``setup()`` method::

    helper = DockerHelper()
    volume = VolumeDefinition('vol02')
    volume.setup(helper=helper)

3. Directly, using the ``set_helper()`` method::

    helper = DockerHelper()
    container = ContainerDefinition('con03', 'nginx:alpine')
    container.set_helper(helper)
    container.setup()

This only needs to be done once for the lifetime of the definition.

For the most part, interaction with Docker should almost entirely occur via the
definitions, but the definition objects need the helpers to actually interact
with Docker.


Mapping to Docker SDK types
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Each resource definition wraps a model from the `Docker SDK for Python`_. The
underlying model can be accessed via the ``inner()`` method, after the resource
has been created. The mapping is as follows:

===================================================  ============================================
Seaworthy resource definition                        Docker SDK model
===================================================  ============================================
:class:`~seaworthy.definitions.ContainerDefinition`  :class:`docker.models.containers.Container`
:class:`~seaworthy.definitions.NetworkDefinition`    :class:`docker.models.networks.Network`
:class:`~seaworthy.definitions.VolumeDefinition`     :class:`docker.models.volumes.Volume`
===================================================  ============================================

Helpers
-------
Resource helpers provide two main functions:

- Namespacing of resources: by prefixing resource names, the resources are
  isolated from other Docker resources already present on the system.
- Teardown (cleanup) of resources: when the tests end, the networks, volumes,
  and containers used in those tests are removed.

In addition, some of the behaviour around resource creation and removal is
changed from the Docker defaults to be a better fit for a testing environment.

Accessing the various helpers is most easily done via the
:class:`~seaworthy.helpers.DockerHelper`::

    from seaworthy.helpers import DockerHelper


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
:func:`docker.client.from_env`.

Mapping to Docker SDK types
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Each resource helper wraps a "model collection" from the Docker SDK. The
underlying collection can be accessed via the ``collection`` attribute. The
mapping is as follows:

===========================================  ======================================================
Seaworthy resource helper                    Docker SDK model collection
===========================================  ======================================================
:class:`~seaworthy.helpers.ContainerHelper`  :class:`docker.models.containers.ContainerCollection`
:class:`~seaworthy.helpers.ImageHelper`      :class:`docker.models.images.ImageCollection`
:class:`~seaworthy.helpers.NetworkHelper`    :class:`docker.models.networks.NetworkCollection`
:class:`~seaworthy.helpers.VolumeHelper`     :class:`docker.models.volumes.VolumeCollection`
===========================================  ======================================================


.. _`Docker SDK for Python`: https://docker-py.readthedocs.io/
