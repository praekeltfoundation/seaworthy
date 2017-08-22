Seaworthy
=========

.. image:: https://img.shields.io/travis/praekeltfoundation/seaworthy/develop.svg?style=flat-square
    :target: https://travis-ci.org/praekeltfoundation/seaworthy

.. image:: https://img.shields.io/codecov/c/github/praekeltfoundation/seaworthy/develop.svg?style=flat-square
    :target: https://codecov.io/github/praekeltfoundation/seaworthy?branch=develop


Test harness for Docker container images

Seaworthy's goals have some overlap with `TestContainers`_, but our current
primary use case is testing the behaviour of Docker images, rather than
providing a way to use Docker containers to test other software. Also,
Seaworthy is written in Python.


Project status
~~~~~~~~~~~~~~
Seaworthy is in the early stages of development and will be undergoing lots of
change. The project was split out of the tests we wrote for our
`docker-django-bootstrap`_ project. There are examples of Seaworthy in use
there.


Optional integrations and testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We have strong opinions about the testing tools we use, and we understand that
other people may have equally strong opinions that differ from ours. For this
reason, we have decided that none of Seaworthy's core functionality will depend
on `pytest`_, `testtools`_, or anything else that might get in the way of how
people might wants to write their tests. On the other hand, we don't want to
reinvent a bunch of integration and helper code for all the third-party testing
tools we like, so we also provide optional integration modules where it makes
sense to do so.

To make sure that none of the optional dependencies accidentally creep into the
core modules (or other optional modules), we have several sets of tests that
run in different environments:

  * `tests-core`: This is a set of core tests that cover basic functionality.
    `tox -e py36-core` will run just these tests in an environment without any
    optional or extra dependencies installed.

  * `tests-testtools`, etc.: These are tests for the optional integration
    modules. `tox -e py36-testtools` will run just the `seaworthy.testtools`
    module's tests in an environment with only the necessary dependencies
    installed, and the other optional integration modules have similar tox
    environments.

  * `tests`: These are general tests that are hard or annoying to write with
    only the minimal dependencies, so we don't have any tooling restrictions
    here. `tox -e py36-full` will run these, as well as all the other test sets
    mentioned above, in an environment with all optional dependencies (and
    potentially some additional test-only dependencies) installed.


.. _`TestContainers`: https://www.testcontainers.org/
.. _`docker-django-bootstrap`: https://github.com/praekeltfoundation/docker-django-bootstrap
.. _`pytest`: https://pytest.org/
.. _`testtools`: https://testtools.readthedocs.io/en/latest/
