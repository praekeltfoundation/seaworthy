Getting started
===============

Installation
------------
Seaworthy can be installed using pip::

    pip install seaworthy

The pytest and testtools integrations can be used if those libraries are
installed, which can be done using extra requirements::

    pip install seaworthy[pytest,testtools]

Defining containers for tests
-----------------------------
Containers can be defined using subclasses of
:class:`~seaworthy.containers.base.ContainerBase`. For example::

    from seaworthy.containers.base import ContainerBase
    from seaworthy.logs import output_lines


    class CakeContainer(ContainerBase):
        IMAGE = 'acme-corp/cake-service:chocolate'
        WAIT_PATTERNS = [
          r'cake \w+ is baked',
          r'cake \w+ is served',
        ]

        def __init__(self, name):
            super().__init__(name, IMAGE, WAIT_PATTERNS)

        # Utility methods can be added to the class to extend functionality
        def exec_cake(self, *params):
            return output_lines(self.inner().exec_run(['cake'] + params))


``WAIT_PATTERNS`` is a list of regex patterns. Once these patterns have been
seen in the container logs, the container is considered to have started and be
ready for use. For more advanced readiness checks, the
:meth:`~ContainerBase.wait_for_start` method.


This container can then be used as fixtures for tests in a number of ways, the
easiest of which is with pytest::

    import pytest


    @pytest.fixture
    def cake_container(docker_helper):
        with CakeContainer('test', helper=docker_helper.containers) as con:
            yield con


    def test_type(cake_container):
        output = cake_container.exec_cake('type')
        assert output = ['chocolate']

A few things to note here:

- The ``docker_helper`` parameter to the ``cake_container`` fixture function is
  a fixture itself and is automatically defined when using pytest with
  Seaworthy. For more information on the helper, see :doc:`helpers`.
- The scope of the fixture is important. By default, pytest fixtures have
  function scope, which means for each test function the fixture is completely
  reinitialized. Creating and starting up a container can be a little slow, so
  you need to think carefully about what scope to use for your fixtures.
