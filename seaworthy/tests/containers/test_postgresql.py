import pytest

from seaworthy.containers.postgresql import PostgreSQLContainer
from seaworthy.pytest import dockertest


@pytest.fixture(scope='module')
def postgresql(docker_helper):
    with PostgreSQLContainer(helper=docker_helper.containers) as container:
        yield container


@dockertest()
class TestPostgreSQLContainer:
    def test_inspection(self, postgresql):
        """
        Inspecting the PostgreSQL container should show that the default image
        and name has been used, all default values have been set correctly in
        the environment variables, a tmpfs is set up in the right place, and
        the network aliases are correct.
        """
        attrs = postgresql.inner().attrs

        assert attrs['Config']['Image'] == PostgreSQLContainer.DEFAULT_IMAGE
        assert attrs['Name'] == '/test_{}'.format(
            PostgreSQLContainer.DEFAULT_NAME)

        env = attrs['Config']['Env']
        assert 'POSTGRES_DB={}'.format(
            PostgreSQLContainer.DEFAULT_DATABASE) in env
        assert 'POSTGRES_USER={}'.format(
            PostgreSQLContainer.DEFAULT_USER) in env
        assert 'POSTGRES_PASSWORD={}'.format(
            PostgreSQLContainer.DEFAULT_PASSWORD) in env

        tmpfs = attrs['HostConfig']['Tmpfs']
        assert tmpfs == {'/var/lib/postgresql/data': 'uid=70,gid=70'}

        network = attrs['NetworkSettings']['Networks']['test_default']
        # The ``short_id`` attribute of the container is the first 10
        # characters, but the network alias is the first 12 :-/
        assert (network['Aliases'] ==
                [PostgreSQLContainer.DEFAULT_NAME, attrs['Id'][:12]])

    def test_list_resources(self, postgresql):
        """
        The methods on the PostgreSQLContainer object that list the database
        resources using ``psql`` should show the database and user have been
        set up.
        """
        assert 'database' in [d[0] for d in postgresql.list_databases()]
        assert postgresql.list_tables() == []
        assert ([r for r in postgresql.list_users() if r[0] == 'user'] ==
                [['user', 'Superuser', '{}']])

    def test_list_tables(self, postgresql):
        """
        We can list tables.
        """
        assert postgresql.list_tables() == []
        postgresql.exec_psql('CREATE TABLE mytable(name varchar(40))')
        assert postgresql.list_tables() == [
            ['public', 'mytable', 'table', 'postgres'],
        ]

    def test_database_url(self):
        """
        The ``database_url`` method should return a single string with all the
        database connection parameters.
        """
        postgresql = PostgreSQLContainer()
        assert postgresql.database_url() == 'postgres://{}:{}@{}/{}'.format(
            PostgreSQLContainer.DEFAULT_USER,
            PostgreSQLContainer.DEFAULT_PASSWORD,
            PostgreSQLContainer.DEFAULT_NAME,
            PostgreSQLContainer.DEFAULT_DATABASE)

        postgresql = PostgreSQLContainer(
            database='db', user='dbuser', password='secret', name='database')
        assert (postgresql.database_url() ==
                'postgres://dbuser:secret@database/db')

    def test_clean(self, postgresql):
        """
        Calling .clean() removes and recreates the default database.
        """
        postgresql.exec_psql('CREATE TABLE mytable(name varchar(40))')
        assert postgresql.list_tables() == [
            ['public', 'mytable', 'table', 'postgres'],
        ]
        postgresql.clean()
        assert postgresql.list_tables() == []
