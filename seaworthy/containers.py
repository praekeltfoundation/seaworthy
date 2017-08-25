from .logs import RegexMatcher, SequentialLinesMatcher, wait_for_logs_matching
from .utils import output_lines


class ContainerBase:
    def __init__(self, name, image, wait_matchers):
        """
        :param name:
            The name for the container. The actual name of the container is
            namespaced by DockerHelper. This name will be used as a network
            alias for the container.
        :param image: image tag to use
        :param list wait_matchers:
            Log matchers to use when checking that the container has started
            successfully.
        """
        self.name = name
        self.image = image
        self.wait_matchers = wait_matchers

        self._container = None

    def create_and_start(self, docker_helper, pull=True):
        """
        Create the container and start it, waiting for the expected log lines.

        :param pull:
            Whether or not to attempt to pull the image if the image tag is not
            known.
        """
        if self._container is not None:
            raise RuntimeError('Container already created.')

        if pull:
            docker_helper.pull_image_if_not_found(self.image)

        self._container = docker_helper.create_container(
            self.name, self.image, **self.create_kwargs())
        docker_helper.start_container(self._container)

        wait_for_logs_matching(
            self._container, SequentialLinesMatcher(*self.wait_matchers))

    def stop_and_remove(self, docker_helper):
        """ Stop the container and remove it. """
        docker_helper.stop_and_remove_container(self.container())
        self._container = None

    def container(self):
        """
        :returns: the underlying Docker container object
        :rtype: docker.models.containers.Container
        """
        if self._container is None:
            raise RuntimeError('Container not created yet.')
        return self._container

    def create_kwargs(self):
        """
        :returns:
            any extra keyword arguments to pass to
            ~DockerHelper.create_container
        :rtype: dict
        """
        return {}

    def clean(self):
        """
        This method should "clean" the container so that it is in the same
        state as it was when it was started.
        """
        raise NotImplementedError()


class PostgreSQLContainer(ContainerBase):
    DEFAULT_NAME = 'postgresql'
    DEFAULT_IMAGE = 'postgres:alpine'
    # The postgres image starts up PostgreSQL twice--the first time to set up
    # the database and user, and the second to actually run the thing.
    DEFAULT_WAIT_MATCHERS = (
        RegexMatcher(r'database system is ready to accept connections'),
        RegexMatcher(r'database system is ready to accept connections'))

    DEFAULT_DATABASE = 'database'
    DEFAULT_USER = 'user'
    DEFAULT_PASSWORD = 'password'

    def __init__(self,
                 name=DEFAULT_NAME,
                 image=DEFAULT_IMAGE,
                 wait_matchers=DEFAULT_WAIT_MATCHERS,
                 database=DEFAULT_DATABASE,
                 user=DEFAULT_USER,
                 password=DEFAULT_PASSWORD):
        """
        :param database: the name of a database to create at startup
        :param user: the name of a user to create at startup
        :param password: the password for the user
        """
        super().__init__(name, image, wait_matchers)

        self.database = database
        self.user = user
        self.password = password

    def create_kwargs(self):
        return {
            'environment': {
                'POSTGRES_DB': self.database,
                'POSTGRES_USER': self.user,
                'POSTGRES_PASSWORD': self.password,
            },
            'tmpfs': {'/var/lib/postgresql/data': 'uid=70,gid=70'},
        }

    def clean(self):
        container = self.container()
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
        return self.container().exec_run(cmd, user='postgres')

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
    DEFAULT_WAIT_MATCHERS = (RegexMatcher(r'Server startup complete'),)

    DEFAULT_VHOST = '/vhost'
    DEFAULT_USER = 'user'
    DEFAULT_PASSWORD = 'password'

    def __init__(self,
                 name=DEFAULT_NAME,
                 image=DEFAULT_IMAGE,
                 wait_matchers=DEFAULT_WAIT_MATCHERS,
                 vhost=DEFAULT_VHOST,
                 user=DEFAULT_USER,
                 password=DEFAULT_PASSWORD):
        """
        :param vhost: the name of a vhost to create at startup
        :param user: the name of a user to create at startup
        :param password: the password for the user
        """
        super().__init__(name, image, wait_matchers)

        self.vhost = vhost
        self.user = user
        self.password = password

    def create_kwargs(self):
        return {
            'environment': {
                'RABBITMQ_DEFAULT_VHOST': self.vhost,
                'RABBITMQ_DEFAULT_USER': self.user,
                'RABBITMQ_DEFAULT_PASS': self.password,
            },
            'tmpfs': {'/var/lib/rabbitmq': 'uid=100,gid=101'},
        }

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
        return self.container().exec_run(cmd)

    def list_vhosts(self):
        """
        Run the ``list_vhosts`` command and return a list of vhost names.
        """
        return output_lines(self.exec_rabbitmqctl('list_vhosts'))

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
