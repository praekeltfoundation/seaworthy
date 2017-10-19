import unittest

import responses

from seaworthy.checks import docker_client, dockertest
from seaworthy.client import ContainerHttpClient
from seaworthy.containers.base import ContainerBase
from seaworthy.dockerhelper import DockerHelper, fetch_images


# Small (<4MB) image that echoes HTTP requests and runs without configuration
IMG = 'jmalloc/echo-server'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    with docker_client() as client:
        fetch_images(client, [IMG])


class DummySession:
    def __init__(self):
        self.requests = []
        self.was_closed = False

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))

    def close(self):
        self.was_closed = True

    def check_was_closed(self):
        was_closed, self.was_closed = self.was_closed, False
        return was_closed


class TestContainerHttpClient(unittest.TestCase):
    def make_helper(self):
        dh = DockerHelper()
        self.addCleanup(dh.teardown)
        dh.setup()
        return dh

    @responses.activate
    def test_defaults(self):
        """
        When the container client is configured with a host address and port,
        requests are made to that address and port.
        """
        client = ContainerHttpClient('127.0.0.1', '12345')

        responses.add(responses.GET, 'http://127.0.0.1:12345/', status=200)
        response = client.request('GET')

        self.assertEqual(response.status_code, 200)

        [call] = responses.calls
        self.assertEqual(call.request.url, 'http://127.0.0.1:12345/')

    @responses.activate
    def test_url_defaults(self):
        """
        When the container client is configured with a host address and port,
        and some URL defaults are set, requests are made to that address and
        port with the expected URL.
        """
        client = ContainerHttpClient('127.0.0.1', '12345', url_defaults={
            'scheme': 'https',
            'fragment': 'test',
        })

        responses.add(responses.GET, 'https://127.0.0.1:12345/baz', status=200)
        response = client.request('GET', ['baz'], url_kwargs={
            'query': (('foo', 'bar'),),
        })

        self.assertEqual(response.status_code, 200)

        [call] = responses.calls
        self.assertEqual(
            call.request.url, 'https://127.0.0.1:12345/baz?foo=bar#test')

    @responses.activate
    def test_methods(self):
        """
        When the HTTP method-specific methods are called, the correct request
        method is used.
        """
        client = ContainerHttpClient('127.0.0.1', '45678')

        responses.add(responses.GET, 'http://127.0.0.1:45678/', status=200)
        responses.add(
            responses.OPTIONS, 'http://127.0.0.1:45678/foo', status=201)
        responses.add(responses.HEAD, 'http://127.0.0.1:45678/bar', status=403)
        responses.add(responses.POST, 'http://127.0.0.1:45678/baz', status=404)
        responses.add(responses.PUT, 'http://127.0.0.1:45678/test', status=418)
        responses.add(
            responses.PATCH, 'http://127.0.0.1:45678/a/b/c', status=501)
        responses.add(
            responses.DELETE, 'http://127.0.0.1:45678/d/e/f', status=503)

        get_response = client.get()
        options_response = client.options(['foo'])
        head_response = client.head(['bar'])
        post_response = client.post(['baz'])
        put_response = client.put(['test'])
        patch_response = client.patch(['a', 'b', 'c'])
        delete_response = client.delete(['d', 'e', 'f'])

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(options_response.status_code, 201)
        self.assertEqual(head_response.status_code, 403)
        self.assertEqual(post_response.status_code, 404)
        self.assertEqual(put_response.status_code, 418)
        self.assertEqual(patch_response.status_code, 501)
        self.assertEqual(delete_response.status_code, 503)

        self.assertEqual(len(responses.calls), 7)

    def test_session(self):
        """
        When a custom session object is given, that object is used to make
        requests and is closed when ``close()`` is called.
        """
        session = DummySession()
        client = ContainerHttpClient('127.0.0.1', '12345', session=session)

        client.request('GET', ['foo'])
        client.request('POST', ['bar'])
        self.assertEqual(session.requests, [
            (('GET', 'http://127.0.0.1:12345/foo'), {}),
            (('POST', 'http://127.0.0.1:12345/bar'), {}),
        ])

        client.close()
        self.assertTrue(session.check_was_closed())

    def test_session_context_manager(self):
        """
        When a custom session object is given, that object is used to make
        requests and is closed when the context is exited when the container
        client is used as a context manager.
        """
        session = DummySession()
        client = ContainerHttpClient('127.0.0.1', '12345', session=session)

        with client:
            client.request('GET', ['foo'])
            self.assertEqual(session.requests, [
                (('GET', 'http://127.0.0.1:12345/foo'), {}),
            ])

        self.assertTrue(session.check_was_closed())

    @dockertest()
    def test_for_container_first_port(self):
        """
        The ``for_container()`` class method returns a container client that
        connects to the container's first port when a specific port is not
        specified.
        """
        dh = self.make_helper()
        container = ContainerBase('first_port', IMG, create_kwargs={
            'ports': {'8080/tcp': ('127.0.0.1', None)}
        })
        container.create_and_start(dh)
        self.addCleanup(container.stop_and_remove, dh)

        client = ContainerHttpClient.for_container(container)

        response = client.request('GET', ['foo'])

        self.assertEqual(response.status_code, 200)
        response_lines = response.text.splitlines()
        self.assertIn('HTTP/1.1 GET /foo', response_lines)

        addr, port = container.get_first_host_port()
        self.assertIn('Host: {}:{}'.format(addr, port), response_lines)

    @dockertest()
    def test_for_container_specific_port(self):
        """
        The ``for_container()`` class method returns a container client that
        connects to the container port specified.
        """
        dh = self.make_helper()
        container = ContainerBase('first_port', IMG, create_kwargs={
            'ports': {
                '8080/tcp': ('127.0.0.1', None),
                '5353/udp': ('127.0.0.1', None),
            }
        })
        container.create_and_start(dh)
        self.addCleanup(container.stop_and_remove, dh)

        client = ContainerHttpClient.for_container(
            container, container_port='8080')

        response = client.request('GET', ['foo'])

        self.assertEqual(response.status_code, 200)
        response_lines = response.text.splitlines()
        self.assertIn('HTTP/1.1 GET /foo', response_lines)

        addr, port = container.get_host_port('8080')
        self.assertIn('Host: {}:{}'.format(addr, port), response_lines)
