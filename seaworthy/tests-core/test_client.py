import unittest

import requests.exceptions

import responses

from seaworthy.checks import docker_client, dockertest
from seaworthy.client import ContainerHttpClient, wait_for_response
from seaworthy.definitions import ContainerDefinition
from seaworthy.helpers import DockerHelper, fetch_images


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
        return dh.containers

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
        response = client.request('GET', '/baz', url_kwargs={
            'query': (('foo', 'bar'),),
        })

        self.assertEqual(response.status_code, 200)

        [call] = responses.calls
        self.assertEqual(
            call.request.url, 'https://127.0.0.1:12345/baz?foo=bar#test')

    @responses.activate
    def test_paths(self):
        """
        The path is appended to the URL correctly with various leading or
        trailing ``/`` characters.
        """
        client = ContainerHttpClient('127.0.0.1', '12345')

        # Root path
        responses.add(responses.GET, 'http://127.0.0.1:12345/', status=200)
        client.request('GET', '')  # Requests adds a trailing /
        client.request('GET', '/')

        self.assertEqual(
            responses.calls[0].request.url, 'http://127.0.0.1:12345/')
        self.assertEqual(
            responses.calls[1].request.url, 'http://127.0.0.1:12345/')

        # Leading slashes are ignored
        responses.add(
            responses.GET, 'http://127.0.0.1:12345/a/b/c', status=200)
        client.request('GET', '/a/b/c')
        client.request('GET', 'a/b/c')

        self.assertEqual(
            responses.calls[2].request.url, 'http://127.0.0.1:12345/a/b/c')
        self.assertEqual(
            responses.calls[3].request.url, 'http://127.0.0.1:12345/a/b/c')

        # Trailing slashes are respected
        responses.add(
            responses.GET, 'http://127.0.0.1:12345/a/b/c/', status=200)
        client.request('GET', '/a/b/c/')

        self.assertEqual(
            responses.calls[4].request.url, 'http://127.0.0.1:12345/a/b/c/')

        # Double slashes are not ignored
        responses.add(
            responses.GET, 'http://127.0.0.1:12345//a//b', status=200)
        client.request('GET', '//a//b')

        self.assertEqual(
            responses.calls[5].request.url, 'http://127.0.0.1:12345//a//b')

    @responses.activate
    def test_relative_paths(self):
        """
        The path can be specified as a relative or absolute path.
        """
        client = ContainerHttpClient(
            '127.0.0.1', '12345', url_defaults={'path': ['foo']})

        responses.add(
            responses.GET, 'http://127.0.0.1:12345/foo/bar/baz', status=200)
        client.request('GET', 'bar/baz')

        self.assertEqual(responses.calls[0].request.url,
                         'http://127.0.0.1:12345/foo/bar/baz')

        responses.add(
            responses.GET, 'http://127.0.0.1:12345/foobar', status=200)
        client.request('GET', '/foobar')

        self.assertEqual(responses.calls[1].request.url,
                         'http://127.0.0.1:12345/foobar')

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
        options_response = client.options('/foo')
        head_response = client.head('/bar')
        post_response = client.post('/baz')
        put_response = client.put('/test')
        patch_response = client.patch('/a/b/c')
        delete_response = client.delete('/d/e/f')

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

        client.request('GET', '/foo')
        client.request('POST', '/bar')
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
            client.request('GET', '/foo')
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
        ch = self.make_helper()
        container = ContainerDefinition('first_port', IMG, create_kwargs={
            'ports': {'8080/tcp': ('127.0.0.1', None)}
        }, helper=ch)
        container.setup()
        self.addCleanup(container.teardown)

        client = ContainerHttpClient.for_container(container)
        self.addCleanup(client.close)

        response = client.request('GET', '/foo')

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
        ch = self.make_helper()
        container = ContainerDefinition('first_port', IMG, create_kwargs={
            'ports': {
                '8080/tcp': ('127.0.0.1', None),
                '5353/udp': ('127.0.0.1', None),
            }
        }, helper=ch)
        container.setup()
        self.addCleanup(container.teardown)

        client = ContainerHttpClient.for_container(
            container, container_port='8080')
        self.addCleanup(client.close)

        response = client.request('GET', '/foo')

        self.assertEqual(response.status_code, 200)
        response_lines = response.text.splitlines()
        self.assertIn('HTTP/1.1 GET /foo', response_lines)

        addr, port = container.get_host_port('8080')
        self.assertIn('Host: {}:{}'.format(addr, port), response_lines)


class TestWaitForResponseFunc(unittest.TestCase):
    @responses.activate
    def test_success(self):
        """
        When a request succeeds before the timeout, all is happy.
        """
        client = ContainerHttpClient('127.0.0.1', '12345')
        responses.add(responses.GET, 'http://127.0.0.1:12345/', status=200)
        # A failure here will raise an exception.
        # 100ms is long enough for a first-time success.
        wait_for_response(client, 0.1)

    @responses.activate
    def test_error_then_success(self):
        """
        When an exception is raised before the timeout, we retry and are happy
        with any successful request before the timeout.
        """
        client = ContainerHttpClient('127.0.0.1', '12345')
        responses.add(
            responses.GET, 'http://127.0.0.1:12345/', body=Exception('KABOOM'))
        responses.add(responses.GET, 'http://127.0.0.1:12345/', status=200)
        # A failure here will raise an exception.
        # Because responses is fast 110ms gives us time to fail, wait 100ms,
        # then succeed.
        wait_for_response(client, 0.11)

    @responses.activate
    def test_error_timeout(self):
        """
        When exceptions are raised without a successful request before the
        timeout, we time out.
        """
        client = ContainerHttpClient('127.0.0.1', '12345')
        responses.add(
            responses.GET, 'http://127.0.0.1:12345/', body=Exception('KABOOM'))
        with self.assertRaises(TimeoutError) as cm:
            # 190ms is enough time to fail, wait 100ms, fail again, wait 100ms,
            # then time out.
            wait_for_response(client, 0.19)
        self.assertEqual(
            str(cm.exception), 'Timeout waiting for HTTP response.')

    @responses.activate
    def test_timeout(self):
        """
        When we don't get a response before the timeout, we time out.

        FIXME: Because responses doesn't do timeouts, we fake it by manually
        raising the exception we expect. We really should use requests itself
        for this.
        """
        client = ContainerHttpClient('127.0.0.1', '12345')

        responses.add(
            responses.GET, 'http://127.0.0.1:12345/',
            body=requests.exceptions.Timeout())
        with self.assertRaises(TimeoutError) as cm:
            # The timeout doesn't actually matter here because we raise the
            # exception ourselves.
            wait_for_response(client, 0.1)
        self.assertEqual(
            str(cm.exception), 'Timeout waiting for HTTP response.')
