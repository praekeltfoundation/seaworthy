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
Containers should be defined using subclasses of
:class:`~seaworthy.definitions.ContainerDefinition`. For example::

    from seaworthy.definitions import ContainerDefinition
    from seaworthy.logs import output_lines


    class CakeContainer(ContainerDefinition):
        IMAGE = 'acme-corp/cake-service:chocolate'
        WAIT_PATTERNS = (
            r'cake \w+ is baked',
            r'cake \w+ is served',
        )

        def __init__(self, name):
            super().__init__(name, IMAGE, WAIT_PATTERNS)

        # Utility methods can be added to the class to extend functionality
        def exec_cake(self, *params):
            return output_lines(self.inner().exec_run(['cake'] + params))


``WAIT_PATTERNS`` is a list of regex patterns. Once these patterns have been
seen in the container logs, the container is considered to have started and be
ready for use. For more advanced readiness checks, the
:meth:`~seaworthy.definitions.ContainerDefinition.wait_for_start` method should
be overridden.

This container can then be used as fixtures for tests in a number of ways, the
easiest of which is with pytest::

    import pytest
    from seaworthy.pytest.fixtures import resource_fixture

    container = CakeContainer('test')
    fixture = resource_fixture(container, 'cake_container')

    def test_type(cake_container):
        output = cake_container.exec_cake('type')
        assert output = ['chocolate']

A few things to note here:

- The :func:`~seaworthy.pytest.fixtures.resource_fixture` function returns a
  pytest fixture that ensures that the container is created and started before
  the test begins and that the container is stopped and removed after the test
  ends.
- The scope of the fixture is important. By default, pytest fixtures have
  function scope, which means that for each test function the fixture is
  completely reinitialized. Creating and starting up a container can be a
  little slow, so you need to think carefully about what scope to use for your
  fixtures. See :meth:`~seaworthy.definitions.ContainerDefinition.clean` for a
  way to avoid container setup/teardown overhead.

For simple cases, :class:`~seaworthy.definitions.ContainerDefinition` can be
used directly, without subclassing::

    container = ContainerDefinition(
        'test', 'acme-corp/soda-service:cola', [r'soda \w+ is fizzing'])
    fixture = resource_fixture(container, 'soda_container')

    def test_refreshment(soda_container):
        assert 'Parpor-Colla Corp' in soda_container.get_logs()

Note that pytest is not required to use Seaworthy and there are several other
ways to use the container as a fixture. For more information see
:doc:`integrations` and :doc:`definitions-helpers`.
