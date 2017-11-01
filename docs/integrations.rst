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
.. _`testtools`: https://testtools.readthedocs.io/en/latest/
