import hyperlink
import requests


class ContainerClient:
    URL_DEFAULTS = {'scheme': 'http'}

    def __init__(self, host, port, url_defaults=None, session_factory=None):
        """
        :param host:
            The address for the host to connect to.
        :param port:
            The port for the host to connect to.
        :param dict url_defaults:
            Parameters to default to in the generated URLs, see
            `~hyperlink.URL`.
        :param session_factory:
            A no-args callable that returns Requests' Session objects.
        """
        if session_factory is None:
            session_factory = requests.Session
        self._session_factory = session_factory

        _url_defaults = self.URL_DEFAULTS.copy()
        if url_defaults is not None:
            _url_defaults.update(url_defaults)
        self._base_url = hyperlink.URL(
            host=host, port=int(port), **_url_defaults)

        self._session = None

    def __enter__(self):
        self._get_session()
        return self

    def close(self):
        """
        Closes the underlying Session object.
        """
        if self._session is not None:
            self._session.close()
            self._session = None

    def __exit__(self, *args):
        self.close()

    def _get_session(self):
        if self._session is None:
            self._session = self._session_factory()

        return self._session

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

    def request(self, method, path, url_kwargs=None, **kwargs):
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
        url_kwargs = url_kwargs if url_kwargs is not None else {}
        url = self._base_url.replace(path=path, **url_kwargs)

        return self._get_session().request(method, url.to_text(), **kwargs)
