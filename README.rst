Seaworthy
=========

.. image:: https://readthedocs.org/projects/seaworthy/badge/?version=latest
    :target: http://seaworthy.readthedocs.io/en/latest/

.. image:: https://travis-ci.org/praekeltfoundation/seaworthy.svg?branch=develop
    :target: https://travis-ci.org/praekeltfoundation/seaworthy

.. image:: https://codecov.io/gh/praekeltfoundation/seaworthy/branch/develop/graph/badge.svg
    :target: https://codecov.io/gh/praekeltfoundation/seaworthy

.. badges

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


.. _`TestContainers`: https://www.testcontainers.org/
.. _`docker-django-bootstrap`: https://github.com/praekeltfoundation/docker-django-bootstrap
