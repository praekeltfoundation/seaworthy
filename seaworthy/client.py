"""
A requests-based HTTP client for interacting with containers that have
forwarded ports.
"""
import time

import hyperlink

import requests


def _path_segments(url, path_str):
    # Absolute path
    if path_str.startswith('/'):
        return path_str[1:].split('/')
    # Relative path
    return url.child(*path_str.split('/')).path


class ContainerHttpClient:
    """
    HTTP client for a specific container.

    In most cases, these should be obtained from
    :meth:`.ContainerDefinition.http_client` instead of being instantiated
    directly.
    """

    URL_DEFAULTS = {'scheme': 'http'}

    def __init__(self, host, port, url_defaults=None, session=None):
        """
        :param host:
            The address for the host to connect to.
        :param port:
            The port for the host to connect to.
        :param dict url_defaults:
            Parameters to default to in the generated URLs, see
            `~hyperlink.URL`.
        :param session:
            A Requests' Session object (or something like it).
        """
        if session is None:
            session = requests.Session()
        self._session = session

        _url_defaults = self.URL_DEFAULTS.copy()
        if url_defaults is not None:
            _url_defaults.update(url_defaults)
        self._base_url = hyperlink.URL(
            host=host, port=int(port), **_url_defaults)

    def __enter__(self):
        return self

    def close(self):
        """
        Closes the underlying Session object.
        """
        self._session.close()

    def __exit__(self, *args):
        self.close()

    @classmethod
    def for_container(cls, container, container_port=None):
        """
        :param container:
            The container to make requests against.
        :param container_port:
            The container port to make requests against. If ``None``, the first
            container port is used.
        :returns:
            A ContainerClient object configured to make requests to the
            container.
        """
        if container_port is not None:
            host, port = container.get_host_port(container_port)
        else:
            host, port = container.get_first_host_port()

        return cls(host, port)

    def _url(self, path, kwargs):
        kwargs = kwargs if kwargs is not None else {}
        if path is not None:
            kwargs['path'] = _path_segments(self._base_url, path)
        return self._base_url.replace(**kwargs).to_text()

    def request(self, method, path=None, url_kwargs=None, **kwargs):
        """
        Make a request against a container.

        :param method:
            The HTTP method to use.
        :param list path:
            The HTTP path (either absolute or relative).
        :param dict url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param kwargs:
            Any other parameters to pass to Requests.
        """
        return self._session.request(
            method, self._url(path, url_kwargs), **kwargs)

    def get(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a GET request.

        :param path:
            The HTTP path (either absolute or relative).
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param **kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.get(self._url(path, url_kwargs), **kwargs)

    def options(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends an OPTIONS request.

        :param path:
            The HTTP path (either absolute or relative).
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param **kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.options(self._url(path, url_kwargs), **kwargs)

    def head(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a HEAD request.

        :param path:
            The HTTP path (either absolute or relative).
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param **kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.head(self._url(path, url_kwargs), **kwargs)

    def post(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a POST request.

        :param path:
            The HTTP path (either absolute or relative).
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param **kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.post(self._url(path, url_kwargs), **kwargs)

    def put(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a PUT request.

        :param path:
            The HTTP path (either absolute or relative).
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param **kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.put(self._url(path, url_kwargs), **kwargs)

    def patch(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a PUT request.

        :param path:
            The HTTP path (either absolute or relative).
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param **kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.patch(self._url(path, url_kwargs), **kwargs)

    def delete(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a PUT request.

        :param path:
            The HTTP path (either absolute or relative).
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param **kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.delete(self._url(path, url_kwargs), **kwargs)


def wait_for_response(client, timeout, path='/', expected_status_code=None):
    """
    Try make a GET request with an HTTP client against a certain path and
    return once any response has been received, ignoring any errors.

    :param ContainerHttpClient client:
        The HTTP client to use to connect to the container.
    :param timeout:
        Timeout value in seconds.
    :param path:
        HTTP path to request.
    :param int expected_status_code:
        If set, wait until a response with this status code is received. If not
        set, the status code will not be checked.
    :raises TimeoutError:
        If a request fails to be made within the timeout period.
    """
    # We want time.monotonic on Pythons that have it, otherwise time.time will
    # have to do.
    get_time = getattr(time, 'monotonic', time.time)

    deadline = get_time() + timeout
    while True:
        try:
            # Don't care what the response is, as long as we get one
            time_left = deadline - get_time()
            response = client.get(
                path, timeout=max(time_left, 0.001), allow_redirects=False)

            if (expected_status_code is None
                    or response.status_code == expected_status_code):
                return
        except requests.exceptions.Timeout:
            # Requests timed out, our time must be up
            break
        except Exception:
            # Ignore other exceptions
            pass

        if get_time() >= deadline:
            break
        time.sleep(0.1)

    raise TimeoutError('Timeout waiting for HTTP response.')
