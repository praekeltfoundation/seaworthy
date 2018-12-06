Seaworthy
=========

.. image:: https://img.shields.io/pypi/v/seaworthy.svg
    :target: https://pypi.org/project/seaworthy/

.. image:: https://readthedocs.org/projects/seaworthy/badge/?version=latest
    :target: http://seaworthy.readthedocs.io/en/latest/

.. image:: https://travis-ci.org/praekeltfoundation/seaworthy.svg?branch=develop
    :target: https://travis-ci.org/praekeltfoundation/seaworthy

.. image:: https://codecov.io/gh/praekeltfoundation/seaworthy/branch/develop/graph/badge.svg
    :target: https://codecov.io/gh/praekeltfoundation/seaworthy

.. badges

Seaworthy is a test harness for Docker container images. It allows you to use
Docker containers and other Docker resources as fixtures for tests written in
Python.

Seaworthy supports Python 3.4 and newer. You can find more information in the
`documentation`_.

A `demo repository`_ is available with a set of Seaworthy tests for a
simple Django application. Seaworthy is also introduced in our `blog post`_ on
continuous integration with Docker on Travis CI.

For more background on the design and purpose of Seaworthy, see our
`PyConZA 2018 talk`_ (`slides`_).


Quick demo
----------
First install Seaworthy along with pytest using pip::

    pip install seaworthy[pytest]

Write some tests in a file, for example, ``test_echo_container.py``:

.. code-block:: python

    from seaworthy.definitions import ContainerDefinition

    container = ContainerDefinition(
        'echo', 'jmalloc/echo-server',
        wait_patterns=[r'Echo server listening on port 8080'],
        create_kwargs={'ports': {'8080': None}})
    fixture = container.pytest_fixture('echo_container')


    def test_echo(echo_container):
        r = echo_container.http_client().get('/foo')
        assert r.status_code == 200
        assert 'HTTP/1.1 GET /foo' in r.text

Run pytest::

    pytest -v test_echo_container.py



Project status
--------------
Seaworthy should be considered alpha-level software. It is well-tested and
works well for the first few things we have used it for, but we would like to
use it for more of our Docker projects, which may require some parts of
Seaworthy to evolve further. See the `project issues`_ for known
issues/shortcomings.

The project was originally split out of the tests we wrote for our
`docker-django-bootstrap`_ project. There are examples of Seaworthy in use
there.


.. _`documentation`: http://seaworthy.readthedocs.io/en/latest/
.. _`demo repository`: https://github.com/JayH5/seaworthy-demo
.. _`blog post`: https://medium.com/mobileforgood/patterns-for-continuous-integration-with-docker-on-travis-ci-ba7e3a5ca2aa
.. _`PyConZA 2018 talk`: https://www.youtube.com/watch?v=NY---NXXHjQ
.. _`slides`: https://speakerdeck.com/jayh5/test-your-docker-images-with-python
.. _`project issues`: https://github.com/praekeltfoundation/seaworthy/issues
.. _`docker-django-bootstrap`: https://github.com/praekeltfoundation/docker-django-bootstrap
