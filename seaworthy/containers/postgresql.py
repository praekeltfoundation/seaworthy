"""
PostgreSQL container definition.
"""

from seaworthy.definitions import ContainerDefinition
from seaworthy.utils import output_lines


class PostgreSQLContainer(ContainerDefinition):
    """
    PostgreSQL container definition.

    .. todo::
       Write more docs.
    """

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

    def base_kwargs(self):
        """
        Add a ``tmpfs`` entry for ``/var/lib/postgresql/data`` to avoid
        unnecessary disk I/O and ``environment`` entries for the configured db
        and user creds.
        """
        return {
            'environment': {
                'POSTGRES_DB': self.database,
                'POSTGRES_USER': self.user,
                'POSTGRES_PASSWORD': self.password,
            },
            'tmpfs': {'/var/lib/postgresql/data': 'uid=70,gid=70'},
        }

    def exec_pg_success(self, cmd):
        """
        Execute a command inside a running container as the postgres user,
        asserting success.
        """
        result = self.inner().exec_run(cmd, user='postgres')
        assert result.exit_code == 0, result.output.decode('utf-8')
        return result

    def clean(self):
        """
        Remove all data by dropping and recreating the configured database.

        .. note::

            Only the configured database is removed. Any other databases
            remain untouched.
        """
        self.exec_pg_success(['dropdb', '-U', self.user, self.database])
        self.exec_pg_success(['createdb', '-U', self.user, self.database])

    def exec_psql(self, command, psql_opts=['-qtA']):
        """
        Execute a ``psql`` command inside a running container. By default the
        container's database is connected to.

        :param command: the command to run (passed to ``-c``)
        :param psql_opts: a list of extra options to pass to ``psql``
        :returns: a tuple of the command exit code and output
        """
        cmd = ['psql'] + psql_opts + [
            '--dbname', self.database,
            '-U', self.user,
            '-c', command,
        ]
        return self.inner().exec_run(cmd, user='postgres')

    def list_databases(self):
        """
        Runs the ``\\list`` command and returns a list of column values with
        information about all databases.
        """
        lines = output_lines(self.exec_psql('\\list'))
        return [line.split('|') for line in lines]

    def list_tables(self):
        """
        Runs the ``\\dt`` command and returns a list of column values with
        information about all tables in the database.
        """
        lines = output_lines(self.exec_psql('\\dt'))
        return [line.split('|') for line in lines]

    def list_users(self):
        """
        Runs the ``\\du`` command and returns a list of column values with
        information about all user roles.
        """
        lines = output_lines(self.exec_psql('\\du'))
        return [line.split('|') for line in lines]

    def database_url(self):
        """
        Returns a "database URL" for use with DJ-Database-URL and similar
        libraries.
        """
        return 'postgres://{}:{}@{}/{}'.format(
            self.user, self.password, self.name, self.database)
