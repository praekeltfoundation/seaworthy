import pytest

from seaworthy.containers.redis import RedisContainer
from seaworthy.pytest import dockertest


@pytest.fixture(scope='module')
def redis(docker_helper):
    with RedisContainer(helper=docker_helper.containers) as container:
        yield container


@dockertest()
class TestRedisContainer:
    def test_inspection(self, redis):
        """
        Inspecting the Redis container should show that the default image
        and name has been used, all default values have been set correctly in
        the environment variables, a tmpfs is set up in the right place, and
        the network aliases are correct.
        """
        attrs = redis.inner().attrs

        assert attrs['Config']['Image'] == RedisContainer.DEFAULT_IMAGE
        assert attrs['Name'] == '/test_{}'.format(
            RedisContainer.DEFAULT_NAME)

        tmpfs = attrs['HostConfig']['Tmpfs']
        assert tmpfs == {'/data': 'uid=100,gid=101'}

        network = attrs['NetworkSettings']['Networks']['test_default']
        # The ``short_id`` attribute of the container is the first 10
        # characters, but the network alias is the first 12 :-/
        assert (network['Aliases'] ==
                [RedisContainer.DEFAULT_NAME, attrs['Id'][:12]])

    def test_list_resources(self, redis):
        """
        The methods on the RedisContainer object that list the database
        resources using ``redis-cli`` should show the default database to be
        empty.
        """
        assert redis.list_keys() == []

    def test_list_keys(self, redis):
        """
        We can list keys in various dbs.
        """
        assert redis.list_keys() == []
        redis.exec_redis_cli('SET', ['x', 1])
        redis.exec_redis_cli('SET', ['y', 2])
        redis.exec_redis_cli('SET', ['z', 3], db=1)
        assert sorted(redis.list_keys()) == sorted(['x', 'y'])
        assert redis.list_keys(db=1) == ['z']

    def test_clean(self, redis):
        """
        Calling .clean() removes all data from all dbs.
        """
        redis.exec_redis_cli('SET', ['x', 1])
        redis.exec_redis_cli('SET', ['y', 2])
        redis.exec_redis_cli('SET', ['z', 3], db=1)
        assert sorted(redis.list_keys()) == sorted(['x', 'y'])
        assert redis.list_keys(db=1) == ['z']
        redis.clean()
        assert redis.list_keys() == []
        assert redis.list_keys(db=1) == []
