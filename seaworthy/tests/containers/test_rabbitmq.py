import json
from urllib.parse import quote as urlquote

import pytest

from seaworthy.containers.rabbitmq import RabbitMQContainer
from seaworthy.pytest import dockertest


@pytest.fixture(scope='module')
def rabbitmq(docker_helper):
    with RabbitMQContainer(docker_helper=docker_helper) as container:
        yield container


@dockertest()
class TestRabbitMQContainer:
    def _setup_management(self, c):
        if getattr(c, '_management_available', False):
            return
        c.inner().exec_run(['apk', 'add', '--no-cache', 'curl'])
        c.inner().exec_run(
            ['rabbitmq-plugins', 'enable', 'rabbitmq_management'])
        c._management_available = True

    def _management_curl(self, c, method, path_parts, data):
        """
        Use curl inside the container to call the management API.

        This is a nasty hack around not having rabbitmqadmin available to us,
        because the container doesn't have Python installed.
        """
        self._setup_management(c)
        cmd = [
            'curl', '-i', '-u', '{}:{}'.format(c.user, c.password),
            '-H', 'content-type:application/json', '-X{}'.format(method),
            '-d{}'.format(json.dumps(data)),
            'http://localhost:15672/api/{}'.format('/'.join(path_parts))]
        return c.inner().exec_run(cmd)

    def declare_queue(self, c, queue_name):
        """
        Use the management API to declare a queue.
        """
        return self._management_curl(
            c, 'PUT',
            ['queues', urlquote(c.vhost, safe=''), queue_name],
            {"auto_delete": False, "durable": False, "arguments": {}})

    def test_inspection(self, rabbitmq):
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
        assert (network['Aliases'] ==
                [RabbitMQContainer.DEFAULT_NAME, attrs['Id'][:12]])

    def test_list_resources(self, rabbitmq):
        """
        The methods on the RabbitMQContainer object that list the AMQP
        resources using ``rabbitmqctl`` should show the vhost and user have
        been set up.
        """
        assert rabbitmq.list_vhosts() == ['/vhost']
        assert rabbitmq.list_users() == [('user', ['administrator'])]
        assert rabbitmq.list_queues() == []

    def test_list_vhosts(self, rabbitmq):
        """
        We can list vhosts.
        """
        assert rabbitmq.list_vhosts() == ['/vhost']
        rabbitmq.exec_rabbitmqctl('add_vhost', ['/new_vhost'])
        assert sorted(rabbitmq.list_vhosts()) == ['/new_vhost', '/vhost']

    def test_list_queues(self, rabbitmq):
        """
        We can list queues.

        NOTE: This test also tests the management API machinery, because
        testing that directly would be very similar and far more annoying.
        """
        assert rabbitmq.list_queues() == []
        self.declare_queue(rabbitmq, "q1")
        self.declare_queue(rabbitmq, "q2")
        assert sorted(rabbitmq.list_queues()) == [('q1', '0'), ('q2', '0')]

    def test_list_users(self, rabbitmq):
        """
        We can list users.
        """
        assert rabbitmq.list_users() == [('user', ['administrator'])]
        rabbitmq.exec_rabbitmqctl('add_user', ['new_user', 'new_pass'])
        assert rabbitmq.list_users() == [
            ('new_user', ['']),
            ('user', ['administrator']),
        ]

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
