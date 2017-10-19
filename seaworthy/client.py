import hyperlink
import requests


class ContainerClient:
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
            kwargs['path'] = path
        return self._base_url.replace(**kwargs).to_text()

    def request(self, method, path=None, url_kwargs=None, **kwargs):
        """
        Make a request against a container.

        :param method:
            The HTTP method to use.
        :param list path:
            A list of segments of the HTTP path.
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
            A list of segments of the HTTP path.
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param \*\*kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.get(self._url(path, url_kwargs), **kwargs)

    def options(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends an OPTIONS request.

        :param path:
            A list of segments of the HTTP path.
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param \*\*kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.options(self._url(path, url_kwargs), **kwargs)

    def head(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a HEAD request.

        :param path:
            A list of segments of the HTTP path.
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param \*\*kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.head(self._url(path, url_kwargs), **kwargs)

    def post(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a POST request.

        :param path:
            A list of segments of the HTTP path.
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param \*\*kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.post(self._url(path, url_kwargs), **kwargs)

    def put(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a PUT request.

        :param path:
            A list of segments of the HTTP path.
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param \*\*kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.put(self._url(path, url_kwargs), **kwargs)

    def patch(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a PUT request.

        :param path:
            A list of segments of the HTTP path.
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param \*\*kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.patch(self._url(path, url_kwargs), **kwargs)

    def delete(self, path=None, url_kwargs=None, **kwargs):
        """
        Sends a PUT request.

        :param path:
            A list of segments of the HTTP path.
        :param url_kwargs:
            Parameters to override in the generated URL. See `~hyperlink.URL`.
        :param \*\*kwargs:
            Optional arguments that ``request`` takes.
        :return: response object
        """
        return self._session.delete(self._url(path, url_kwargs), **kwargs)
