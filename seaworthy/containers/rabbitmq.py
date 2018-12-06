"""
RabbitMQ container definition.
"""

from seaworthy.definitions import ContainerDefinition
from seaworthy.utils import output_lines


def _parse_rabbitmq_user(user_line):
    user, tags = user_line.split('\t', 1)
    tags = tags.strip('[]').split(', ')
    return (user, tags)


class RabbitMQContainer(ContainerDefinition):
    """
    RabbitMQ container definition.

    .. todo::
       Write more docs.
    """

    # For some reason this container is slower to start through seaworthy than
    # with a plain `docker run`, so give it a bit more time to get going. :-(
    WAIT_TIMEOUT = 20.0

    DEFAULT_NAME = 'rabbitmq'
    DEFAULT_IMAGE = 'rabbitmq:alpine'
    DEFAULT_WAIT_PATTERNS = (r'Server startup complete',)

    DEFAULT_VHOST = '/vhost'
    DEFAULT_USER = 'user'
    DEFAULT_PASSWORD = 'password'

    def __init__(self,
                 name=DEFAULT_NAME,
                 image=DEFAULT_IMAGE,
                 wait_patterns=DEFAULT_WAIT_PATTERNS,
                 vhost=DEFAULT_VHOST,
                 user=DEFAULT_USER,
                 password=DEFAULT_PASSWORD,
                 **kwargs):
        """
        :param vhost: the name of a vhost to create at startup
        :param user: the name of a user to create at startup
        :param password: the password for the user
        """
        super().__init__(name, image, wait_patterns, **kwargs)

        self.vhost = vhost
        self.user = user
        self.password = password

    def base_kwargs(self):
        """
        Add a ``tmpfs`` entry for ``/var/lib/rabbitmq`` to avoid unnecessary
        disk I/O and ``environment`` entries for the configured vhost and user
        creds.
        """
        return {
            'environment': {
                'RABBITMQ_DEFAULT_VHOST': self.vhost,
                'RABBITMQ_DEFAULT_USER': self.user,
                'RABBITMQ_DEFAULT_PASS': self.password,
            },
            'tmpfs': {'/var/lib/rabbitmq': 'uid=100,gid=101'},
        }

    def clean(self):
        """
        Remove all data by using ``rabbitmqctl`` to eval
        ``rabbit_mnesia:reset()``.
        """
        reset_erl = 'rabbit:stop(), rabbit_mnesia:reset(), rabbit:start().'
        self.exec_rabbitmqctl('eval', [reset_erl])

    def exec_rabbitmqctl(self, command, args=[], rabbitmqctl_opts=['-q']):
        """
        Execute a ``rabbitmqctl`` command inside a running container.

        :param command: the command to run
        :param args: a list of args for the command
        :param rabbitmqctl_opts:
            a list of extra options to pass to ``rabbitmqctl``
        :returns: a tuple of the command exit code and output
        """
        cmd = ['rabbitmqctl'] + rabbitmqctl_opts + [command] + args
        return self.inner().exec_run(cmd)

    def list_vhosts(self):
        """
        Run the ``list_vhosts`` command and return a list of vhost names.
        """
        return output_lines(self.exec_rabbitmqctl('list_vhosts'))

    def list_queues(self):
        """
        Run the ``list_queues`` command (for the default vhost) and return a
        list of tuples describing the queues.

        :return:
            A list of 2-element tuples. The first element is the queue name,
            the second is the current queue size.
        """
        lines = output_lines(
            self.exec_rabbitmqctl('list_queues', ['-p', self.vhost]))
        return [tuple(line.split(None, 1)) for line in lines]

    def list_users(self):
        """
        Run the ``list_users`` command and return a list of tuples describing
        the users.

        :return:
            A list of 2-element tuples. The first element is the username, the
            second a list of tags for the user.
        """
        lines = output_lines(self.exec_rabbitmqctl('list_users'))
        return [_parse_rabbitmq_user(line) for line in lines]

    def broker_url(self):
        """ Returns a "broker URL" for use with Celery. """
        return 'amqp://{}:{}@{}/{}'.format(
            self.user, self.password, self.name, self.vhost)
