from urllib.parse import quote as urlquote

import pytest

from seaworthy.containers.rabbitmq import RabbitMQContainer
from seaworthy.pytest import dockertest


@pytest.fixture(scope='module')
def rabbitmq(docker_helper):
    container = RabbitMQContainer(
        create_kwargs={'ports': {'15672/tcp': ('127.0.0.1',)}},
        container_helper=docker_helper.containers)
    with container:
        container.inner().exec_run(
            ['rabbitmq-plugins', 'enable', 'rabbitmq_management'])
        yield container


@dockertest()
class TestRabbitMQContainer:
    _http_client = None

    def _management_req(self, c, method, path_parts, data):
        """
        Make an HTTP call to the management API.

        This is a hack around not having rabbitmqadmin available to us, because
        the container doesn't have Python installed.
        """
        if self._http_client is None:
            self._http_client = c.http_client()
        path = 'api/{}'.format('/'.join(path_parts))
        resp = self._http_client.request(
            method, path, json=data, auth=(c.user, c.password))
        resp.raise_for_status()
        return resp

    def declare_queue(self, c, queue_name):
        """
        Use the management API to declare a queue.
        """
        return self._management_req(
            c, 'PUT', ['queues', urlquote(c.vhost, safe=''), queue_name],
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

    def test_clean(self, rabbitmq):
        """
        Calling .clean() removes all stored state.
        """
        rabbitmq.exec_rabbitmqctl('add_vhost', ['/new_vhost'])
        assert '/new_vhost' in rabbitmq.list_vhosts()
        self.declare_queue(rabbitmq, "q1")
        assert ('q1', '0') in rabbitmq.list_queues()
        rabbitmq.exec_rabbitmqctl('add_user', ['new_user', 'new_pass'])
        assert ('new_user', ['']) in rabbitmq.list_users()

        rabbitmq.clean()

        assert rabbitmq.list_vhosts() == ['/vhost']
        assert rabbitmq.list_users() == [('user', ['administrator'])]
        assert rabbitmq.list_queues() == []
