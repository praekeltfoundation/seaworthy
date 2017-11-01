Frequently asked questions
==========================

What are the similarities between Seaworthy and docker-compose?
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
Seaworthy does try to reuse some of the default behaviour that docker-compose
implements in order to make it easier and faster to start running containers.

* All Docker resources (networks, volumes, containers) are namespaced by
  prefixing the resource name, e.g. a container called ``cake-service`` could
  be namespaced to have the name ``test_cake-service``.
* A new bridge network is created by default for containers where no network is
  specified.
* Containers are given network aliases with their names, making it easier to
  connect one container to another.

Both Seaworthy and docker-compose are built using the official `Docker SDK for
Python`_.


...what are the differences?
""""""""""""""""""""""""""""
Seaworthy is fundamentally designed for a different purpose. docker-compose
uses YAML files to define Docker resources—it does not have an API for this.
With Seaworthy, all Docker resources are created *programmatically*, typically
as fixtures for tests.

Seaworthy includes functionality specific to its purpose:

* Predictable setup/teardown processes for all resources.
* Various utilities for inspecting running containers, e.g. for matching
  log output, for listing running processes, or for making HTTP requests
  against containers.
* Integrations with popular Python testing libraries (`pytest`_ and
  `testtools`_).

Seaworthy currently lacks some of the functionality of docker-compose:

* The ability to build images for containers
* Any sort of Docker Swarm functionality
* Any concept of multiple instances of containers
* Probably other things...


What about building images?
"""""""""""""""""""""""""""
Seaworthy doesn't currently implement an interface for building images. In most
cases, we expect users to build their images in a previous step of their
continuous integration process and then use Seaworthy to test that image.
However, there may be cases where having Seaworthy build Docker images would
make sense, such as if an image is built purely to be used in tests.


.. _`Docker SDK for Python`: https://docker-py.readthedocs.io/
.. _`pytest`: https://pytest.org/
.. _`testtools`: https://testtools.readthedocs.io/
