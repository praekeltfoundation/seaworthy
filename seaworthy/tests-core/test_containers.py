import unittest

from docker.models.containers import Container

from seaworthy.checks import dockertest
from seaworthy.containers import (
    ContainerBase, PostgreSQLContainer, RabbitMQContainer)
from seaworthy.dockerhelper import DockerHelper

IMG = 'nginx:alpine'
docker_helper = DockerHelper()


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    docker_helper.setup()
    docker_helper.pull_image_if_not_found(IMG)


@dockertest()
def tearDownModule():  # noqa: N802
    docker_helper.teardown()


@dockertest()
class TestContainerBase(unittest.TestCase):
    def setUp(self):
        self.base = ContainerBase('test', IMG)

    def test_create_only_if_not_created(self):
        """The container cannot be created more than once."""
        self.base.create_and_start(docker_helper, pull=False)

        # We can't create the container when it's already created
        with self.assertRaises(RuntimeError) as cm:
            self.base.create_and_start(docker_helper, pull=False)
        self.assertEqual(str(cm.exception), 'Container already created.')

        self.base.stop_and_remove(docker_helper)

    def test_remove_only_if_created(self):
        """The container can only be removed if it has been created."""
        self.base.create_and_start(docker_helper, pull=False)

        # We can remove the container if it's created
        self.base.stop_and_remove(docker_helper)

        with self.assertRaises(RuntimeError) as cm:
            self.base.stop_and_remove(docker_helper)
        self.assertEqual(str(cm.exception), 'Container not created yet.')

    def test_container_only_if_created(self):
        """
        We can only access the inner Container object if the container has been
        created.
        """
        # If we try get the container before it's created it'll fail
        with self.assertRaises(RuntimeError) as cm:
            self.base.inner()
        self.assertEqual(str(cm.exception), 'Container not created yet.')

        self.base.create_and_start(docker_helper, pull=False)

        # We can get the container once it's created
        container = self.base.inner()
        self.assertIsInstance(container, Container)

        self.base.stop_and_remove(docker_helper)
        with self.assertRaises(RuntimeError) as cm:
            self.base.inner()
        self.assertEqual(str(cm.exception), 'Container not created yet.')

    def test_default_create_kwargs(self):
        """
        The default return value of the ``create_kwargs`` method is an empty
        dict.
        """
        self.assertEqual(self.base.create_kwargs(), {})

    def test_default_clean(self):
        """By default, the ``clean`` method raises a NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.base.clean()


@dockertest()
class TestPostgreSQLContainer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.postgresql = PostgreSQLContainer()
        cls.postgresql.create_and_start(docker_helper)

    @classmethod
    def tearDownClass(cls):
        cls.postgresql.stop_and_remove(docker_helper)

    def test_inspection(self):
        """
        Inspecting the PostgreSQL container should show that the default image
        and name has been used, all default values have been set correctly in
        the environment variables, a tmpfs is set up in the right place, and
        the network aliases are correct.
        """
        attrs = self.postgresql.inner().attrs

        self.assertEqual(attrs['Config']['Image'],
                         PostgreSQLContainer.DEFAULT_IMAGE)
        self.assertEqual(attrs['Name'], '/test_{}'.format(
            PostgreSQLContainer.DEFAULT_NAME))

        env = attrs['Config']['Env']
        self.assertIn('POSTGRES_DB={}'.format(
            PostgreSQLContainer.DEFAULT_DATABASE), env)
        self.assertIn('POSTGRES_USER={}'.format(
            PostgreSQLContainer.DEFAULT_USER), env)
        self.assertIn('POSTGRES_PASSWORD={}'.format(
            PostgreSQLContainer.DEFAULT_PASSWORD), env)

        tmpfs = attrs['HostConfig']['Tmpfs']
        self.assertEqual(tmpfs, {'/var/lib/postgresql/data': 'uid=70,gid=70'})

        network = attrs['NetworkSettings']['Networks']['test_default']
        # The ``short_id`` attribute of the container is the first 10
        # characters, but the network alias is the first 12 :-/
        self.assertEqual(network['Aliases'], [
            PostgreSQLContainer.DEFAULT_NAME, attrs['Id'][:12]])

    def test_list_resources(self):
        """
        The methods on the PostgreSQLContainer object that list the database
        resources using ``psql`` should show the database and user have been
        set up.
        """
        self.assertIn('database',
                      [d[0] for d in self.postgresql.list_databases()])
        self.assertEqual(self.postgresql.list_tables(), [])
        self.assertEqual(
            [r for r in self.postgresql.list_users() if r[0] == 'user'],
            [['user', 'Superuser', '{}']])

    def test_database_url(self):
        """
        The ``database_url`` method should return a single string with all the
        database connection parameters.
        """
        postgresql = PostgreSQLContainer()
        self.assertEqual(
            postgresql.database_url(), 'postgres://{}:{}@{}/{}'.format(
                PostgreSQLContainer.DEFAULT_USER,
                PostgreSQLContainer.DEFAULT_PASSWORD,
                PostgreSQLContainer.DEFAULT_NAME,
                PostgreSQLContainer.DEFAULT_DATABASE))

        postgresql = PostgreSQLContainer(
            database='db', user='dbuser', password='secret', name='database')
        self.assertEqual(
            postgresql.database_url(), 'postgres://dbuser:secret@database/db')


@dockertest()
class TestRabbitMQContainer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rabbitmq = RabbitMQContainer()
        cls.rabbitmq.create_and_start(docker_helper)

    @classmethod
    def tearDownClass(cls):
        cls.rabbitmq.stop_and_remove(docker_helper)

    def test_inspection(self):
        """
        Inspecting the RabbitMQ container should show that the default image
        and name has been used, all default values have been set correctly in
        the environment variables, a tmpfs is set up in the right place, and
        the network aliases are correct.
        """
        attrs = self.rabbitmq.inner().attrs

        self.assertEqual(attrs['Config']['Image'],
                         RabbitMQContainer.DEFAULT_IMAGE)
        self.assertEqual(attrs['Name'],
                         '/test_{}'.format(RabbitMQContainer.DEFAULT_NAME))

        env = attrs['Config']['Env']
        self.assertIn('RABBITMQ_DEFAULT_VHOST={}'.format(
            RabbitMQContainer.DEFAULT_VHOST), env)
        self.assertIn('RABBITMQ_DEFAULT_USER={}'.format(
            RabbitMQContainer.DEFAULT_USER), env)
        self.assertIn('RABBITMQ_DEFAULT_PASS={}'.format(
            RabbitMQContainer.DEFAULT_PASSWORD), env)

        tmpfs = attrs['HostConfig']['Tmpfs']
        self.assertEqual(tmpfs, {'/var/lib/rabbitmq': 'uid=100,gid=101'})

        network = attrs['NetworkSettings']['Networks']['test_default']
        # The ``short_id`` attribute of the container is the first 10
        # characters, but the network alias is the first 12 :-/
        self.assertEqual(network['Aliases'],
                         [RabbitMQContainer.DEFAULT_NAME, attrs['Id'][:12]])

    def test_list_resources(self):
        """
        The methods on the RabbitMQContainer object that list the AMQP
        resources using ``rabbitmqctl`` should show the vhost and user have
        been set up.
        """
        self.assertEqual(self.rabbitmq.list_vhosts(), ['/vhost'])
        self.assertEqual(
            self.rabbitmq.list_users(), [('user', ['administrator'])])
        self.assertEqual(self.rabbitmq.list_policies(), [])

    def test_broker_url(self):
        """
        The ``broker_url`` method should return a single string with all the
        vhost connection parameters.
        """
        rabbitmq = RabbitMQContainer()
        self.assertEqual(
            rabbitmq.broker_url(), 'amqp://{}:{}@{}/{}'.format(
                RabbitMQContainer.DEFAULT_USER,
                RabbitMQContainer.DEFAULT_PASSWORD,
                RabbitMQContainer.DEFAULT_NAME,
                RabbitMQContainer.DEFAULT_VHOST))

        rabbitmq = RabbitMQContainer(
            vhost='/', user='guest', password='guest', name='amqp')
        self.assertEqual(rabbitmq.broker_url(), 'amqp://guest:guest@amqp//')
