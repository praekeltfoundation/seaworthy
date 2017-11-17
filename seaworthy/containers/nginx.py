from seaworthy.client import wait_for_response
from seaworthy.definitions import ContainerDefinition


class NginxContainer(ContainerDefinition):
    """
    Nginx container definition.

    .. todo:
        Write more docs.
    """

    DEFAULT_NAME = 'nginx'
    DEFAULT_IMAGE = 'nginx:alpine'

    def __init__(self, name=DEFAULT_NAME, image=DEFAULT_IMAGE, **kwargs):
        super().__init__(name, image, **kwargs)

    def base_kwargs(self):
        """
        Publish all exposed ports to the host.
        """
        return {'publish_all_ports': True}

    def wait_for_start(self):
        """
        Wait for Nginx to return any valid HTTP response.
        """
        wait_for_response(self.http_client(), self.wait_timeout)

    def exec_nginx(self, args):
        """
        Execute a ``nginx`` command inside a running container.

        :params args: a list of args for the command
        """
        return self.inner().exec_run(['nginx'] + args)

    def exec_signal(self, signal='reload'):
        """
        Send a signal to the Nginx master process (``nginx -s``).

        :param signal: one of: stop, quit, reopen, or reload
        """
        return self.exec_nginx(['-s', signal])
