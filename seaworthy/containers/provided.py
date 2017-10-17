import json
from urllib.parse import quote as urlquote

from seaworthy.logs import output_lines
from .base import ContainerBase, deep_merge


class PostgreSQLContainer(ContainerBase):
    DEFAULT_NAME = 'postgresql'
    DEFAULT_IMAGE = 'postgres:alpine'
    # The postgres image starts up PostgreSQL twice--the first time to set up
    # the database and user, and the second to actually run the thing.
    DEFAULT_WAIT_PATTERNS = (
        r'database system is ready to accept connections',
        r'database system is ready to accept connections',)

    DEFAULT_DATABASE = 'database'
    DEFAULT_USER = 'user'
    DEFAULT_PASSWORD = 'password'

    def __init__(self,
                 name=DEFAULT_NAME,
                 image=DEFAULT_IMAGE,
                 wait_patterns=DEFAULT_WAIT_PATTERNS,
                 database=DEFAULT_DATABASE,
                 user=DEFAULT_USER,
                 password=DEFAULT_PASSWORD,
                 **kwargs):
        """
        :param database: the name of a database to create at startup
        :param user: the name of a user to create at startup
        :param password: the password for the user
        """
        super().__init__(name, image, wait_patterns, **kwargs)

        self.database = database
        self.user = user
        self.password = password

    def merge_kwargs(self, default_kwargs, kwargs):
        base_kwargs = {
            'environment': {
                'POSTGRES_DB': self.database,
                'POSTGRES_USER': self.user,
                'POSTGRES_PASSWORD': self.password,
            },
            'tmpfs': {'/var/lib/postgresql/data': 'uid=70,gid=70'},
        }
        return deep_merge(base_kwargs, default_kwargs, kwargs)

    def clean(self):
        container = self.inner()
        container.exec_run(['dropdb', self.database], user='postgres')
        container.exec_run(
            ['createdb', '-O', self.user, self.database], user='postgres')

    def exec_psql(self, command, psql_opts=['-qtA']):
        """
        Execute a ``psql`` command inside a running container. By default the
        container's database is connected to.

        :param command: the command to run (passed to ``-c``)
        :param psql_opts: a list of extra options to pass to ``psql``
        """
        cmd = ['psql'] + psql_opts + ['--dbname', self.database, '-c', command]
        return self.inner().exec_run(cmd, user='postgres')

    def list_databases(self):
        """
        Runs the ``\list`` command and returns a list of column values with
        information about all databases.
        """
        lines = output_lines(self.exec_psql('\list'))
        return [line.split('|') for line in lines]

    def list_tables(self):
        """
        Runs the ``\dt`` command and returns a list of column values with
        information about all tables in the database.
        """
        lines = output_lines(self.exec_psql('\dt'))
        return [line.split('|') for line in lines]

    def list_users(self):
        """
        Runs the ``\du`` command and returns a list of column values with
        information about all user roles.
        """
        lines = output_lines(self.exec_psql('\du'))
        return [line.split('|') for line in lines]

    def database_url(self):
        """
        Returns a "database URL" for use with DJ-Database-URL and similar
        libraries.
        """
        return 'postgres://{}:{}@{}/{}'.format(
            self.user, self.password, self.name, self.database)


def _parse_rabbitmq_user(user_line):
    user_tags = user_line.split('\t', 1)
    if len(user_tags) != 2:
        raise RuntimeError()

    user, tags = user_tags
    tags = tags.strip('[]').split(', ')
    return (user, tags)


class RabbitMQContainer(ContainerBase):
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

        self._management_available = False

        self.vhost = vhost
        self.user = user
        self.password = password

    def merge_kwargs(self, default_kwargs, kwargs):
        base_kwargs = {
            'environment': {
                'RABBITMQ_DEFAULT_VHOST': self.vhost,
                'RABBITMQ_DEFAULT_USER': self.user,
                'RABBITMQ_DEFAULT_PASS': self.password,
            },
            'tmpfs': {'/var/lib/rabbitmq': 'uid=100,gid=101'},
        }
        return deep_merge(base_kwargs, default_kwargs, kwargs)

    def clean(self):
        reset_erl = 'rabbit:stop(), rabbit_mnesia:reset(), rabbit:start().'
        self.exec_rabbitmqctl('eval', [reset_erl])

    def exec_rabbitmqctl(self, command, command_opts=[],
                         rabbitmqctl_opts=['-q']):
        """
        Execute a ``rabbitmqctl`` command inside a running container.

        :param command: the command to run
        :param command_opts: a list of extra options to pass to the command
        :param rabbitmqctl_opts:
            a list of extra options to pass to ``rabbitmqctl``
        """
        cmd = ['rabbitmqctl'] + rabbitmqctl_opts + [command] + command_opts
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

    def list_policies(self):
        """
        Run the ``list_policies`` command and return a list of policies for the
        vhost.
        """
        return output_lines(
            self.exec_rabbitmqctl('list_policies', ['-p', self.vhost]))

    def broker_url(self):
        """ Returns a "broker URL" for use with Celery. """
        return 'amqp://{}:{}@{}/{}'.format(
            self.user, self.password, self.name, self.vhost)

    def _setup_management(self):
        """
        Enable the management API plugin and install curl.
        """
        if self._management_available:
            return
        self.inner().exec_run(['apk', 'add', '--update', 'curl'])
        self.inner().exec_run(
            ['rabbitmq-plugins', 'enable', 'rabbitmq_management'])
        self._management_available = True

    def _management_curl(self, method, path_parts, data=None):
        """
        Use curl inside the container to call the management API.

        This is a nasty hack around not having rabbitmqadmin available to us,
        because the container doesn't have Python installed.
        """
        self._setup_management()
        cmd = [
            'curl', '-i', '-u', '{}:{}'.format(self.user, self.password),
            '-H', 'content-type:application/json', '-X{}'.format(method),
            'http://localhost:15672/api/{}'.format('/'.join(path_parts))]
        if data is not None:
            cmd.append('-d{}'.format(json.dumps(data)))
        return self.inner().exec_run(cmd)

    def declare_queue(self, queue_name):
        """
        Use the management API to declare a queue.
        """
        return self._management_curl(
            'PUT',
            ['queues', urlquote(self.vhost, safe=''), queue_name],
            {"auto_delete": False, "durable": False, "arguments": {}})
