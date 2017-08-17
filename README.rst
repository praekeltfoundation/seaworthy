seaworthy
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


.. _`TestContainers`: https://www.testcontainers.org/
.. _`docker-django-bootstrap`: https://github.com/praekeltfoundation/docker-django-bootstrap
