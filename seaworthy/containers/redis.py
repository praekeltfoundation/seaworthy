"""
Redis container definition.
"""

from seaworthy.definitions import ContainerDefinition
from seaworthy.utils import output_lines


class RedisContainer(ContainerDefinition):
    """
    Redis container definition.

    .. todo::
       Write more docs.
    """

    DEFAULT_NAME = 'redis'
    DEFAULT_IMAGE = 'redis:alpine'
    DEFAULT_WAIT_PATTERNS = (r'\* Ready to accept connections',)

    def __init__(self,
                 name=DEFAULT_NAME,
                 image=DEFAULT_IMAGE,
                 wait_patterns=DEFAULT_WAIT_PATTERNS,
                 **kwargs):
        super().__init__(name, image, wait_patterns, **kwargs)

    def base_kwargs(self):
        """
        Add a ``tmpfs`` entry for ``/data`` to avoid unnecessary disk I/O.
        """
        return {'tmpfs': {'/data': 'uid=100,gid=101'}}

    def clean(self):
        """
        Remove all data by sending the ``FLUSHALL`` command.
        """
        self.exec_redis_cli('FLUSHALL')

    def exec_redis_cli(self, command, args=[], db=0, redis_cli_opts=[]):
        """
        Execute a ``redis-cli`` command inside a running container.

        :param command: the command to run
        :param args: a list of args for the command
        :param db: the db number to query (default ``0``)
        :param redis_cli_opts: a list of extra options to pass to ``redis-cli``
        :returns: a tuple of the command exit code and output
        """
        cli_opts = ['-n', str(db)] + redis_cli_opts
        cmd = ['redis-cli'] + cli_opts + [command] + [str(a) for a in args]
        return self.inner().exec_run(cmd)

    def list_keys(self, pattern='*', db=0):
        """
        Run the ``KEYS`` command and return the list of matching keys.

        :param pattern: the pattern to filter keys by (default ``*``)
        :param db: the db number to query (default ``0``)
        """
        lines = output_lines(self.exec_redis_cli('KEYS', [pattern], db=db))
        return [] if lines == [''] else lines
