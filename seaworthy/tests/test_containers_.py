import pytest

from seaworthy.containers import RabbitMQContainer
from seaworthy.dockerhelper import DockerHelper
from seaworthy.pytest import dockertest


@pytest.fixture(scope='module')
def docker_helper():
    docker_helper = DockerHelper()
    docker_helper.setup()
    yield docker_helper
    docker_helper.teardown()


def container_fixture(name, container):
    @pytest.fixture(name=name, scope='class')
    def fixture(docker_helper):
        container.create_and_start(docker_helper)
        yield container
        container.stop_and_remove(docker_helper)

    return fixture


rabbitmq = container_fixture('rabbitmq', RabbitMQContainer())


@dockertest()
class TestRabbitMQContainer:
    def test_inspection(self, docker_helper, rabbitmq):
        """
        Inspecting the RabbitMQ container should show that the default image
        and name has been used, all default values have been set correctly in
        the environment variables, a tmpfs is set up in the right place, and
        the network aliases are correct.
        """
        attrs = rabbitmq.inner().attrs

        assert attrs['Config']['Image'] == RabbitMQContainer.DEFAULT_IMAGE
        assert attrs['Name'] == '/test_{}'.format(
            RabbitMQContainer.DEFAULT_NAME)

        env = attrs['Config']['Env']
        assert 'RABBITMQ_DEFAULT_VHOST={}'.format(
            RabbitMQContainer.DEFAULT_VHOST) in env
        assert 'RABBITMQ_DEFAULT_USER={}'.format(
            RabbitMQContainer.DEFAULT_USER) in env
        assert 'RABBITMQ_DEFAULT_PASS={}'.format(
            RabbitMQContainer.DEFAULT_PASSWORD) in env

        tmpfs = attrs['HostConfig']['Tmpfs']
        assert tmpfs == {'/var/lib/rabbitmq': 'uid=100,gid=101'}

        network = attrs['NetworkSettings']['Networks']['test_default']
        # The ``short_id`` attribute of the container is the first 10
        # characters, but the network alias is the first 12 :-/
        assert network['Aliases'] == [
            RabbitMQContainer.DEFAULT_NAME, attrs['Id'][:12]]

    def test_list_resources(self, rabbitmq):
        """
        The methods on the RabbitMQContainer object that list the AMQP
        resources using ``rabbitmqctl`` should show the vhost and user have
        been set up.
        """
        assert rabbitmq.list_vhosts() == ['/vhost']
        assert rabbitmq.list_users() == [('user', ['administrator'])]
        assert rabbitmq.list_policies() == []

    def test_broker_url(self):
        """
        The ``broker_url`` method should return a single string with all the
        vhost connection parameters.
        """
        rabbitmq = RabbitMQContainer()
        assert rabbitmq.broker_url() == 'amqp://{}:{}@{}/{}'.format(
            RabbitMQContainer.DEFAULT_USER,
            RabbitMQContainer.DEFAULT_PASSWORD,
            RabbitMQContainer.DEFAULT_NAME,
            RabbitMQContainer.DEFAULT_VHOST)

        rabbitmq = RabbitMQContainer(
            vhost='/', user='guest', password='guest', name='amqp')
        assert rabbitmq.broker_url() == 'amqp://guest:guest@amqp//'
