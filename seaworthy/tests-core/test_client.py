import unittest

import responses

from seaworthy.checks import docker_client, dockertest
from seaworthy.client import ContainerClient
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
        self.closes = 0

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))

    def close(self):
        self.closes += 1


class DummySessionFactory:
    def __init__(self):
        self.sessions = []

    def __call__(self):
        session = DummySession()
        self.sessions.append(session)
        return session


class TestContainerClient(unittest.TestCase):
    def make_helper(self):
        dh = DockerHelper()
        self.addCleanup(dh.teardown)
        dh.setup()
        return dh

    @responses.activate
    def test_defaults(self):
        """
        When the container client is configured with a host address and port,
        requests are made against that address and port.
        """
        client = ContainerClient('127.0.0.1', '12345')

        responses.add(responses.GET, 'http://127.0.0.1:12345/', status=200)
        response = client.request('GET', [])

        self.assertEqual(response.status_code, 200)

        self.assertEqual(len(responses.calls), 1)
        [call] = responses.calls
        self.assertEqual(call.request.url, 'http://127.0.0.1:12345/')

    @responses.activate
    def test_url_defaults(self):
        """
        When the container client is configured with a host address and port,
        and some URL defaults are set, requests are made agains that address
        and port with the expected URL.
        """
        client = ContainerClient('127.0.0.1', '12345', url_defaults={
            'scheme': 'https',
            'fragment': 'test',
        })

        responses.add(responses.GET, 'https://127.0.0.1:12345/baz', status=200)
        response = client.request('GET', ['baz'], url_kwargs={
            'query': (('foo', 'bar'),),
        })

        self.assertEqual(response.status_code, 200)

        self.assertEqual(len(responses.calls), 1)
        [call] = responses.calls
        self.assertEqual(
            call.request.url, 'https://127.0.0.1:12345/baz?foo=bar#test')

    def test_session_factory(self):
        """
        The session factory is used to create sessions when a request is made.
        Calling close on the client results in the session being closed.
        Requests made after the session is closed result in a new session being
        created.
        """
        session_factory = DummySessionFactory()
        client = ContainerClient(
            '127.0.0.1', '12345', session_factory=session_factory)

        self.assertEqual(len(session_factory.sessions), 0)

        # Making a request creates a session
        client.request('GET', ['foo'])
        client.request('POST', ['bar'])
        self.assertEqual(len(session_factory.sessions), 1)
        [session] = session_factory.sessions
        self.assertEqual(session.requests, [
            (('GET', 'http://127.0.0.1:12345/foo'), {}),
            (('POST', 'http://127.0.0.1:12345/bar'), {}),
        ])

        self.assertEqual(session.closes, 0)
        client.close()
        self.assertEqual(session.closes, 1)

        client.request('PUT', ['baz'])
        self.assertEqual(len(session_factory.sessions), 2)
        session2 = session_factory.sessions[1]
        self.assertEqual(session2.requests, [
            (('PUT', 'http://127.0.0.1:12345/baz'), {}),
        ])

        client.close()
        self.assertEqual(session2.closes, 1)

    def test_session_factory_context_manager(self):
        """
        The container client can be used as a context manager. In this case,
        the session is created when the context is entered, and closed when the
        context is exited.
        """
        session_factory = DummySessionFactory()
        client = ContainerClient(
            '127.0.0.1', '12345', session_factory=session_factory)

        with client:
            self.assertEqual(len(session_factory.sessions), 1)
            [session] = session_factory.sessions

            client.request('GET', ['foo'])
            self.assertEqual(session.requests, [
                (('GET', 'http://127.0.0.1:12345/foo'), {}),
            ])

        self.assertEqual(session.closes, 1)

    def test_session_close_multiple_times(self):
        """
        The ``close()`` method can be called multiple times with no effect
        after it has been called once.
        """
        session_factory = DummySessionFactory()
        client = ContainerClient(
            '127.0.0.1', '12345', session_factory=session_factory)

        client.request('GET', [])
        self.assertEqual(len(session_factory.sessions), 1)

        client.close()
        self.assertEqual(session_factory.sessions[0].closes, 1)

        # We can call close lots of times and nothing happens
        client.close()
        client.close()
        self.assertEqual(session_factory.sessions[0].closes, 1)

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

        client = ContainerClient.for_container(container)

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

        client = ContainerClient.for_container(
            container, container_port='8080')

        response = client.request('GET', ['foo'])

        self.assertEqual(response.status_code, 200)
        response_lines = response.text.splitlines()
        self.assertIn('HTTP/1.1 GET /foo', response_lines)

        addr, port = container.get_host_port('8080')
        self.assertIn('Host: {}:{}'.format(addr, port), response_lines)
