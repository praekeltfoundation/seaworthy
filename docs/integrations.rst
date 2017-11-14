Test framework integration
==========================
We have strong opinions about the testing tools we use, and we understand that
other people may have equally strong opinions that differ from ours. For this
reason, we have decided that none of Seaworthy's core functionality will depend
on `pytest`_, `testtools`_, or anything else that might get in the way of how
people might wants to write their tests. On the other hand, we don't want to
reinvent a bunch of integration and helper code for all the third-party testing
tools we like, so we also provide optional integration modules where it makes
sense to do so.

pytest
------
Seaworthy is a `pytest plugin`_ and all the functions and fixtures in the
:mod:`seaworthy.pytest` module will be available when Seaworthy is used with
pytest.

``docker_helper`` fixture
^^^^^^^^^^^^^^^^^^^^^^^^^
A fixture for a :class:`~seaworthy.helpers.DockerHelper` instance is defined by
default. This fixture uses all the ``DockerHelper`` defaults and has
module-level scope. The behaviour of this fixture can be overridden by defining
a new ``docker_helper`` fixture using
:func:`~seaworthy.pytest.fixtures.docker_helper_fixture`.

``dockertest`` decorator
^^^^^^^^^^^^^^^^^^^^^^^^
The :func:`~seaworthy.pytest.checks.dockertest` decorator can be used to mark
tests that *require* Docker to run. These tests will be skipped if Docker is
not available. It's possible that some tests in your test suite may not require
Docker and you may want to still be able to run your tests in an environment
that does not have Docker available. The decorator can be used as follows::

    @dockertest()
    def test_docker_thing(cake_container):
        assert cake_container.exec_cake('variant') == ['gateau']

Fixture factories
^^^^^^^^^^^^^^^^^
A few functions are provided in the :mod:`seaworthy.pytest.fixtures` module
that are factories for fixtures. The most important two are:

.. autofunction:: seaworthy.pytest.fixtures.container_fixture
    :noindex:

.. autofunction:: seaworthy.pytest.fixtures.clean_container_fixtures
    :noindex:


testtools
---------
We primarily use testtools when matching against complex data structures and
don't use any of its test runner functionality. Currently, testtools matchers
are only used for matching :class:`~seaworthy.ps.PsTree` objects. See the API
documentation for the :mod:`seaworthy.ps` module.


Testing our integrations
------------------------
To make sure that none of the optional dependencies accidentally creep into the
core modules (or other optional modules), we have several sets of tests that
run in different environments:

* ``tests-core``: This is a set of core tests that cover basic functionality.
  ``tox -e py36-core`` will run just these tests in an environment without any
  optional or extra dependencies installed.

* ``tests-pytest``, etc.: These are tests for the optional pytest integration
  modules. ``tox -e py36-testtools`` will run just the ``seaworthy.pytest``
  modules' tests in an environment with only the necessary dependencies
  installed.

* ``tests-testtools``, etc.: These are tests for the optional testtools
  integration module. ``tox -e py36-testtools`` will run just the
  ``seaworthy.testtools`` module's tests.

* ``tests``: These are general tests that are hard or annoying to write with
  only the minimal dependencies, so we don't have any tooling restrictions
  here. ``tox -e py36-full`` will run these, as well as all the other test sets
  mentioned above, in an environment with all optional dependencies (and
  potentially some additional test-only dependencies) installed.


.. _`pytest`: https://pytest.org/
.. _`pytest plugin`: https://docs.pytest.org/en/latest/plugins.html
.. _`testtools`: https://testtools.readthedocs.io/en/latest/
