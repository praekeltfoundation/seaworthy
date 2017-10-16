import tempfile
import unittest

import docker

from seaworthy.checks import docker_client, dockertest
from seaworthy.dockerhelper import DockerHelper, fetch_images


# We use this image to test with because it is a small (~7MB) image from
# https://github.com/docker-library/official-images that runs indefinitely with
# no configuration.
IMG = 'nginx:alpine'


@dockertest()
def setUpModule():  # noqa: N802 (The camelCase is mandated by unittest.)
    with docker_client() as client:
        fetch_images(client, [IMG])


def filter_by_name(things, prefix):
    return [t for t in things if t.name.startswith(prefix)]


@dockertest()
class TestDockerHelper(unittest.TestCase):
    def setUp(self):
        self.client = docker.client.from_env()
        self.addCleanup(self.client.api.close)

    def make_helper(self, *args, setup=True, **kwargs):
        """
        Create and return a DockerHelper instance that will be cleaned up after
        the test.
        """
        dh = DockerHelper(*args, **kwargs)
        self.addCleanup(dh.teardown)
        if setup:
            dh.setup()
        return dh

    def list_networks(self, *args, namespace='test', **kw):
        return filter_by_name(
            self.client.networks.list(*args, **kw), '{}_'.format(namespace))

    def list_containers(self, *args, namespace='test', **kw):
        return filter_by_name(
            self.client.containers.list(*args, **kw), '{}_'.format(namespace))

    def list_volumes(self, *args, namespace='test', **kw):
        return filter_by_name(
            self.client.volumes.list(*args, **kw), '{}_'.format(namespace))

    def test_default_network_lifecycle(self):
        """
        The default network can only be created once and is removed during
        teardown.
        """
        dh = self.make_helper()
        # The default network isn't created unless required
        network = dh.get_default_network(create=False)
        self.assertIsNone(network)

        # Create the default network
        network = dh.get_default_network(create=True)
        self.assertIsNotNone(network)

        # We can try to get the network lots of times and we get the same one
        # and new ones aren't created.
        dh.get_default_network(create=False)
        dh.get_default_network(create=True)
        networks = self.list_networks()
        self.assertEqual(networks, [network])

        # The default network is removed on teardown
        dh.teardown()
        network = dh.get_default_network(create=False)
        self.assertIsNone(network)

    def test_default_network_already_exists(self):
        """
        If the default network already exists when we try to create it, we
        fail.
        """
        # We use a separate DockerHelper (with the usual cleanup) to create the
        # test network so that the DockerHelper under test will see that it
        # already exists.
        dh1 = self.make_helper()
        dh1.get_default_network()
        # Now for the test.
        dh2 = self.make_helper()
        with self.assertRaises(docker.errors.APIError) as cm:
            dh2.get_default_network()
        self.assertIn('network', str(cm.exception))
        self.assertIn('already exists', str(cm.exception))

    def test_teardown_safe(self):
        """
        DockerHelper.teardown() is safe to call multiple times, both before and
        after setup.

        There are no assertions here. We only care that calling teardown never
        raises any exceptions.
        """
        dh = self.make_helper(setup=False)
        # These should silently do nothing.
        dh.teardown()
        dh.teardown()
        # Run setup so we have something to tear down.
        dh.setup()
        # This should do the teardown.
        dh.teardown()
        # This should silently do nothing.
        dh.teardown()

    def test_teardown_containers(self):
        """
        DockerHelper.teardown() will remove any containers that were created,
        no matter what state they are in or even whether they still exist.
        """
        dh = self.make_helper()
        self.assertEqual([], self.list_containers(all=True))
        con_created = dh.create_container('created', IMG)
        self.assertEqual(con_created.status, 'created')

        con_running = dh.create_container('running', IMG)
        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')

        con_stopped = dh.create_container('stopped', IMG)
        dh.start_container(con_stopped)
        self.assertEqual(con_stopped.status, 'running')
        dh.stop_container(con_stopped)
        self.assertNotEqual(con_stopped.status, 'running')

        con_removed = dh.create_container('removed', IMG)
        # We remove this behind the helper's back so the helper thinks it still
        # exists at teardown time.
        con_removed.remove()
        with self.assertRaises(docker.errors.NotFound):
            con_removed.reload()

        self.assertEqual(
            set([con_created, con_running, con_stopped]),
            set(self.list_containers(all=True)))

        with self.assertLogs('seaworthy', level='WARNING') as cm:
            dh.teardown()
        self.assertEqual(sorted(l.getMessage() for l in cm.records), [
            "Container 'test_created' still existed during teardown",
            "Container 'test_running' still existed during teardown",
            "Container 'test_stopped' still existed during teardown",
        ])
        self.assertEqual([], self.list_containers(all=True))

    def test_teardown_networks(self):
        """
        DockerHelper.teardown() will remove any networks that were created,
        even if they no longer exist.
        """
        dh = self.make_helper()
        self.assertEqual([], self.list_networks())
        net_bridge1 = dh.create_network('bridge1', driver='bridge')
        net_bridge2 = dh.create_network('bridge2', driver='bridge')

        net_removed = dh.create_network('removed')
        # We remove this behind the helper's back so the helper thinks it still
        # exists at teardown time.
        net_removed.remove()
        with self.assertRaises(docker.errors.NotFound):
            net_removed.reload()

        self.assertEqual(
            set([net_bridge1, net_bridge2]),
            set(self.list_networks()))

        with self.assertLogs('seaworthy', level='WARNING') as cm:
            dh.teardown()
        self.assertEqual(sorted(l.getMessage() for l in cm.records), [
            "Network 'test_bridge1' still existed during teardown",
            "Network 'test_bridge2' still existed during teardown",
        ])
        self.assertEqual([], self.list_networks())

    def test_teardown_volumes(self):
        """
        DockerHelper.teardown() will remove any volumes that were created,
        even if they no longer exist.
        """
        dh = self.make_helper()
        self.assertEqual([], self.list_networks())
        vol_local1 = dh.create_volume('local1', driver='local')
        vol_local2 = dh.create_volume('local2', driver='local')

        vol_removed = dh.create_volume('removed')
        # We remove this behind the helper's back so the helper thinks it still
        # exists at teardown time.
        vol_removed.remove()
        with self.assertRaises(docker.errors.NotFound):
            vol_removed.reload()

        self.assertEqual(
            set([vol_local1, vol_local2]),
            set(self.list_volumes()))

        with self.assertLogs('seaworthy', level='WARNING') as cm:
            dh.teardown()
        self.assertEqual(sorted(l.getMessage() for l in cm.records), [
            "Volume 'test_local1' still existed during teardown",
            "Volume 'test_local2' still existed during teardown",
        ])
        self.assertEqual([], self.list_volumes())

    def test_create_container(self):
        """
        We can create a container with various parameters without starting it.
        """
        dh = self.make_helper()

        con_simple = dh.create_container('simple', IMG)
        self.addCleanup(dh.remove_container, con_simple)
        self.assertEqual(con_simple.status, 'created')
        self.assertEqual(con_simple.attrs['Path'], 'nginx')

        con_cmd = dh.create_container('cmd', IMG, command='echo hello')
        self.addCleanup(dh.remove_container, con_cmd)
        self.assertEqual(con_cmd.status, 'created')
        self.assertEqual(con_cmd.attrs['Path'], 'echo')

        con_env = dh.create_container('env', IMG, environment={'FOO': 'bar'})
        self.addCleanup(dh.remove_container, con_env)
        self.assertEqual(con_env.status, 'created')
        self.assertIn('FOO=bar', con_env.attrs['Config']['Env'])

    def test_create_network(self):
        """
        We can create a network with various parameters.
        """
        dh = self.make_helper()

        net_simple = dh.create_network('simple')
        self.addCleanup(dh.remove_network, net_simple)
        self.assertEqual(net_simple.name, 'test_simple')
        self.assertEqual(net_simple.attrs['Driver'], 'bridge')
        self.assertEqual(net_simple.attrs['Internal'], False)

        net_internal = dh.create_network('internal', internal=True)
        self.addCleanup(dh.remove_network, net_internal)
        self.assertEqual(net_internal.name, 'test_internal')
        self.assertEqual(net_internal.attrs['Internal'], True)

        # Copy custom IPAM/subnet example from Docker docs:
        # https://docker-py.readthedocs.io/en/2.5.1/networks.html#docker.models.networks.NetworkCollection.create
        ipam_pool = docker.types.IPAMPool(
            subnet='192.168.52.0/24', gateway='192.168.52.254')
        ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])
        net_subnet = dh.create_network('subnet', ipam=ipam_config)
        self.assertEqual(net_subnet.name, 'test_subnet')
        self.addCleanup(dh.remove_network, net_subnet)
        config = net_subnet.attrs['IPAM']['Config'][0]
        self.assertEqual(config['Subnet'], '192.168.52.0/24')
        self.assertEqual(config['Gateway'], '192.168.52.254')

    def test_create_volume(self):
        """
        We can create a volume with various parameters.
        """
        dh = self.make_helper()

        vol_simple = dh.create_volume('simple')
        self.addCleanup(dh.remove_volume, vol_simple)
        self.assertEqual(vol_simple.name, 'test_simple')
        self.assertEqual(vol_simple.attrs['Driver'], 'local')

        vol_labels = dh.create_volume('labels', labels={'foo': 'bar'})
        self.addCleanup(dh.remove_volume, vol_labels)
        self.assertEqual(vol_labels.name, 'test_labels')
        self.assertEqual(vol_labels.attrs['Labels'], {'foo': 'bar'})

        # Copy tmpfs example from Docker docs:
        # https://docs.docker.com/engine/reference/commandline/volume_create/#driver-specific-options
        # This won't work on Windows
        driver_opts = {
            'type': 'tmpfs', 'device': 'tmpfs', 'o': 'size=100m,uid=1000'}
        vol_opts = dh.create_volume(
            'opts', driver='local', driver_opts=driver_opts)
        self.addCleanup(dh.remove_volume, vol_opts)
        self.assertEqual(vol_opts.name, 'test_opts')
        self.assertEqual(vol_opts.attrs['Options'], driver_opts)

    def test_container_network(self):
        """
        When a container is created, the network settings are respected, and if
        no network settings are specified, the container is connected to a
        default network.
        """
        dh = self.make_helper()

        # When 'network' is provided, that network is used
        custom_network = dh.create_network('network')
        self.addCleanup(dh.remove_network, custom_network)
        con_network = dh.create_container(
            'network', IMG, network=custom_network)
        self.addCleanup(dh.remove_container, con_network)
        networks = con_network.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [custom_network.name])
        network = networks[custom_network.name]
        self.assertCountEqual(
            network['Aliases'], [con_network.id[:12], 'network'])

        # When 'network_mode' is provided, the default network is not used
        con_mode = dh.create_container('mode', IMG, network_mode='none')
        self.addCleanup(dh.remove_container, con_mode)
        networks = con_mode.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), ['none'])

        # When 'network_disabled' is True, the default network is not used
        con_disabled = dh.create_container(
            'disabled', IMG, network_disabled=True)
        self.addCleanup(dh.remove_container, con_disabled)
        self.assertEqual(con_disabled.attrs['NetworkSettings']['Networks'], {})

        con_default = dh.create_container('default', IMG)
        self.addCleanup(dh.remove_container, con_default)
        default_network_name = dh.get_default_network().name
        networks = con_default.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [default_network_name])
        network = networks[default_network_name]
        self.assertCountEqual(
            network['Aliases'], [con_default.id[:12], 'default'])

    def test_container_network_by_id(self):
        """
        When a container is created, a network can be specified using the ID
        string for a network.
        """
        dh = self.make_helper()

        # When 'network' is provided as an ID, that network is used
        net_id = dh.create_network('id')
        self.addCleanup(dh.remove_network, net_id)
        con_id = dh.create_container('id', IMG, network=net_id.id)
        self.addCleanup(dh.remove_container, con_id)
        networks = con_id.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_id.name])
        network = networks[net_id.name]
        self.assertCountEqual(network['Aliases'], [con_id.id[:12], 'id'])

    def test_container_network_by_short_id(self):
        """
        When a container is created, a network can be specified using the short
        ID string for a network.
        """
        dh = self.make_helper()

        # When 'network' is provided as a short ID, that network is used
        net_short_id = dh.create_network('short_id')
        self.addCleanup(dh.remove_network, net_short_id)
        con_short_id = dh.create_container(
            'short_id', IMG, network=net_short_id.short_id)
        self.addCleanup(dh.remove_container, con_short_id)
        networks = con_short_id.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_short_id.name])
        network = networks[net_short_id.name]
        self.assertCountEqual(
            network['Aliases'], [con_short_id.id[:12], 'short_id'])

    def test_container_network_by_name(self):
        """
        When a container is created, a network can be specified using the name
        of a network.
        """
        dh = self.make_helper()

        # When 'network' is provided as a name, that network is used
        net_name = dh.create_network('name')
        self.addCleanup(dh.remove_network, net_name)
        con_name = dh.create_container('name', IMG, network=net_name.name)
        self.addCleanup(dh.remove_container, con_name)
        networks = con_name.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_name.name])
        network = networks[net_name.name]
        self.assertCountEqual(network['Aliases'], [con_name.id[:12], 'name'])

    def test_container_network_by_invalid_type(self):
        """
        When a container is created, an error is raised if a network is
        specified using an invalid type.
        """
        dh = self.make_helper()

        with self.assertRaises(ValueError) as cm:
            dh.create_container('invalid_type', IMG, network=42)

        self.assertEqual(
            str(cm.exception),
            "Unexpected type <class 'int'>, expected <class 'str'> or <class "
            "'docker.models.networks.Network'>")

    def test_container_volumes(self):
        """
        When a container is created, a volume can be specified to be mounted.
        The container metadata should correctly identify the volumes and its
        mountpoint.
        """
        dh = self.make_helper()

        vol_test = dh.create_volume('test')
        self.addCleanup(dh.remove_volume, vol_test)
        con_volumes = dh.create_container(
            'volumes', IMG, volumes={vol_test: {'bind': '/vol', 'mode': 'rw'}})
        self.addCleanup(dh.remove_container, con_volumes)
        mounts = con_volumes.attrs['Mounts']
        self.assertEqual(len(mounts), 1)
        [mount] = mounts
        self.assertEqual(mount['Type'], 'volume')
        self.assertEqual(mount['Name'], vol_test.name)
        self.assertEqual(mount['Source'], vol_test.attrs['Mountpoint'])
        self.assertEqual(mount['Driver'], vol_test.attrs['Driver'])
        self.assertEqual(mount['Destination'], '/vol')
        self.assertEqual(mount['Mode'], 'rw')

    def test_container_volumes_bind(self):
        """
        When a container is created, a bind mount can be specified in the
        ``volumes`` hash. The container metadata should correctly describe the
        bind mount.
        """
        dh = self.make_helper()

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        con_bind = dh.create_container(
            'bind', IMG, volumes={tmpdir.name: {'bind': '/vol', 'mode': 'rw'}})
        self.addCleanup(dh.remove_container, con_bind)
        mounts = con_bind.attrs['Mounts']
        self.assertEqual(len(mounts), 1)
        [mount] = mounts
        self.assertEqual(mount['Type'], 'bind')
        self.assertEqual(mount['Source'], tmpdir.name)
        self.assertEqual(mount['Destination'], '/vol')
        self.assertTrue(mount['RW'])

    def test_container_volumes_by_name(self):
        """
        When a container is created, volumes can be specified using volume
        names. Volumes don't have IDs, only names :-/
        """
        dh = self.make_helper()

        # When 'volumes' is provided as a mapping from names, those volumes are
        # used
        vol_name = dh.create_volume('name')
        self.addCleanup(dh.remove_volume, vol_name)
        con_name = dh.create_container(
            'name', IMG,
            volumes={vol_name.name: {'bind': '/vol', 'mode': 'rw'}})
        self.addCleanup(dh.remove_container, con_name)
        mounts = con_name.attrs['Mounts']
        self.assertEqual(len(mounts), 1)
        [mount] = mounts
        self.assertEqual(mount['Name'], vol_name.name)

    def test_container_volumes_by_invalid_type(self):
        """
        When a container is created, an error is raised if a volume is
        specified using an invalid type.
        """
        dh = self.make_helper()

        with self.assertRaises(ValueError) as cm:
            dh.create_container(
                'invalid_type', IMG,
                volumes={42: {'bind': '/vol', 'mode': 'rw'}})

        self.assertEqual(
            str(cm.exception),
            "Unexpected type <class 'int'>, expected <class 'str'> or <class "
            "'docker.models.volumes.Volume'>")

    def test_container_volumes_specified_twice(self):
        """
        When a container is created, an error is raised if the same volume is
        specified twice: once using its string ID, and once using its model
        object.
        """
        dh = self.make_helper()

        # When 'volumes' is provided as a mapping from names, those volumes are
        # used
        vol_duplicate = dh.create_volume('duplicate')
        self.addCleanup(dh.remove_volume, vol_duplicate)
        with self.assertRaises(ValueError) as cm:
            dh.create_container(
                'duplicate', IMG,
                volumes={
                    vol_duplicate.name: {'bind': '/vol', 'mode': 'rw'},
                    vol_duplicate: {'bind': '/vol2', 'mode': 'ro'},
                })

        self.assertEqual(str(cm.exception),
                         "Volume 'test_duplicate' specified more than once")

    def test_start_container(self):
        """
        We can start a container after creating it.
        """
        dh = self.make_helper()

        con = dh.create_container('con', IMG)
        self.addCleanup(dh.remove_container, con)
        self.assertEqual(con.status, 'created')
        dh.start_container(con)
        self.assertEqual(con.status, 'running')

    def test_stop_container(self):
        """
        We can stop a running container.
        """
        # We don't test the timeout because that's just passed directly through
        # to docker and it's nontrivial to construct a container that takes a
        # specific amount of time to stop.
        dh = self.make_helper()

        con = dh.create_container('con', IMG)
        self.addCleanup(dh.remove_container, con)
        dh.start_container(con)
        self.assertEqual(con.status, 'running')
        dh.stop_container(con)
        self.assertEqual(con.status, 'exited')

    def test_remove_container(self):
        """
        We can remove a not-running container.
        """
        dh = self.make_helper()

        con_created = dh.create_container('created', IMG)
        self.assertEqual(con_created.status, 'created')
        dh.remove_container(con_created)
        with self.assertRaises(docker.errors.NotFound):
            con_created.reload()

        con_stopped = dh.create_container('stopped', IMG)
        dh.start_container(con_stopped)
        dh.stop_container(con_stopped)
        self.assertEqual(con_stopped.status, 'exited')
        dh.remove_container(con_stopped)
        with self.assertRaises(docker.errors.NotFound):
            con_stopped.reload()

    def test_remove_container_force(self):
        """
        We can't remove a running container without forcing it.
        """
        dh = self.make_helper()

        con_running = dh.create_container('running', IMG)
        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')
        with self.assertRaises(docker.errors.APIError):
            dh.remove_container(con_running, force=False)
        dh.remove_container(con_running)
        with self.assertRaises(docker.errors.NotFound):
            con_running.reload()

    def test_stop_and_remove_container(self):
        """
        This does the stop and remove as separate steps, so we can remove a
        running container without forcing.
        """
        dh = self.make_helper()

        con_running = dh.create_container('running', IMG)
        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')
        dh.stop_and_remove_container(con_running, remove_force=False)
        with self.assertRaises(docker.errors.NotFound):
            con_running.reload()

    def test_remove_network(self):
        """
        We can remove a network.
        """
        dh = self.make_helper()

        net_test = dh.create_network('test')
        dh.remove_network(net_test)
        with self.assertRaises(docker.errors.NotFound):
            net_test.reload()

    def test_remove_network_connected_to_created_container(self):
        """
        We can remove a network when it is connected to a container if the
        container hasn't been started yet.
        """
        dh = self.make_helper()

        net_test = dh.create_network('test')

        con_created = dh.create_container('created', IMG, network=net_test)
        self.addCleanup(dh.remove_container, con_created)
        self.assertEqual(con_created.status, 'created')
        networks = con_created.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_test.name])

        # Container not yet started so not listed as container connected to
        # network
        net_test.reload()
        self.assertEqual(net_test.containers, [])

        # Container not yet started so we can remove the network
        dh.remove_network(net_test)
        with self.assertRaises(docker.errors.NotFound):
            net_test.reload()

        # The container will still think it's connected to the network
        con_created.reload()
        networks = con_created.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_test.name])
        # But... we can't disconnect it from the old one

    def test_cannot_remove_network_connected_to_running_container(self):
        """
        We cannot remove a network when it is connected to a container if the
        container has been started. Once the container is disconnected, the
        network can be removed.
        """
        dh = self.make_helper()

        # Create a network and connect it to a container
        net_test = dh.create_network('test')
        con_running = dh.create_container('running', IMG, network=net_test)
        networks = con_running.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_test.name])

        # Start the container, now the network should know about it
        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')
        net_test.reload()
        self.assertEqual(net_test.containers, [con_running])

        with self.assertRaises(docker.errors.APIError) as cm:
            dh.remove_network(net_test)
        self.assertIn('network', str(cm.exception))
        self.assertIn('has active endpoints', str(cm.exception))

        # Once the container is disconnected, the network can be removed
        net_test.disconnect(con_running)
        dh.remove_network(net_test)

        with self.assertRaises(docker.errors.NotFound):
            net_test.reload()

    def test_remove_network_connected_to_stopped_container(self):
        """
        We can remove a network when it is connected to a container if the
        container has been stopped.
        """
        dh = self.make_helper()

        # Create a network and connect it to a container
        net_test = dh.create_network('test')
        con_stopped = dh.create_container('stopped', IMG, network=net_test)
        networks = con_stopped.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_test.name])

        # Stop the container
        dh.start_container(con_stopped)
        dh.stop_container(con_stopped)
        self.assertEqual(con_stopped.status, 'exited')

        net_test.reload()
        self.assertEqual(net_test.containers, [])
        dh.remove_network(net_test)

        with self.assertRaises(docker.errors.NotFound):
            net_test.reload()

    def test_remove_volume(self):
        """
        We can remove a volume.
        """
        dh = self.make_helper()

        vol_test = dh.create_volume('test')
        dh.remove_volume(vol_test)
        with self.assertRaises(docker.errors.NotFound):
            vol_test.reload()

    def test_cannot_remove_mounted_volume(self):
        """
        We can't remove a volume mounted to a container no matter what state
        the container is in. Once the container has been removed, we can remove
        the volume.
        """
        dh = self.make_helper()

        vol_created = dh.create_volume('created')
        con_created = dh.create_container(
            'created', IMG,
            volumes={vol_created: {'bind': '/vol', 'mode': 'rw'}})
        self.assertEqual(con_created.status, 'created')

        # Try remove the volume... we can't
        with self.assertRaises(docker.errors.APIError) as cm:
            dh.remove_volume(vol_created)
        self.assertIn('volume is in use', str(cm.exception))

        # Remove the container and then the volume
        dh.remove_container(con_created)
        dh.remove_volume(vol_created)

        vol_running = dh.create_volume('running')
        con_running = dh.create_container(
            'running', IMG,
            volumes={vol_running: {'bind': '/vol', 'mode': 'rw'}})

        dh.start_container(con_running)
        self.assertEqual(con_running.status, 'running')

        # Try remove the volume... we can't
        with self.assertRaises(docker.errors.APIError) as cm:
            dh.remove_volume(vol_running)
        self.assertIn('volume is in use', str(cm.exception))

        # Remove the container and then the volume
        dh.remove_container(con_running)
        dh.remove_volume(vol_running)

        vol_stopped = dh.create_volume('stopped')
        con_stopped = dh.create_container(
            'stopped', IMG,
            volumes={vol_stopped: {'bind': '/vol', 'mode': 'rw'}})

        dh.start_container(con_stopped)
        dh.stop_container(con_stopped)
        self.assertEqual(con_stopped.status, 'exited')

        # Try remove the volume... we can't
        with self.assertRaises(docker.errors.APIError) as cm:
            dh.remove_volume(vol_stopped)
        self.assertIn('volume is in use', str(cm.exception))

        # Remove the container and then the volume
        dh.remove_container(con_stopped)
        dh.remove_volume(vol_stopped)

    def test_cannot_force_remove_mounted_volume(self):
        """
        We can't remove a volume mounted to a container even if we use
        ``force=True``.

        The Docker Engine API reference doesn't describe the force flag in much
        detail:
        "Force the removal of the volume"
        https://docs.docker.com/engine/api/v1.32/#operation/VolumeDelete

        The Docker Python client docs describe the force flag as:
        "Force removal of volumes that were already removed out of band by the
        volume driver plugin."
        https://docker-py.readthedocs.io/en/2.5.1/volumes.html#docker.models.volumes.Volume.remove
        """
        dh = self.make_helper()

        vol_test = dh.create_volume('test')
        self.addCleanup(dh.remove_volume, vol_test)
        con_created = dh.create_container(
            'created', IMG, volumes={vol_test: {'bind': '/vol', 'mode': 'rw'}})
        self.addCleanup(dh.remove_container, con_created)
        self.assertEqual(con_created.status, 'created')

        # Try remove the volume... we can't
        with self.assertRaises(docker.errors.APIError) as cm:
            dh.remove_volume(vol_test, force=True)
        self.assertIn('volume is in use', str(cm.exception))

    def test_remove_container_with_volume(self):
        """
        When a volume is mounted to a container, and the container is removed,
        the volume itself is not removed.
        """
        dh = self.make_helper()

        vol_removed = dh.create_volume('removed')
        dh.addCleanup(dh.remove_volume, vol_removed)
        con_removed = dh.create_container(
            'removed', IMG,
            volumes={vol_removed: {'bind': '/vol', 'mode': 'rw'}})

        dh.remove_container(con_removed)
        with self.assertRaises(docker.errors.NotFound):
            con_removed.reload()

        # The volume still exists: we can fetch it
        vol_removed.reload()

    def test_pull_image_if_not_found(self):
        """
        We check if the image is already present and pull it if necessary.
        """
        dh = self.make_helper()

        # First, remove the image if it's already present. (We use the busybox
        # image for this test because it's the smallest I can find that is
        # likely to be reliably available.)
        try:
            self.client.images.get('busybox:latest')
        except docker.errors.ImageNotFound:  # pragma: no cover
            pass
        else:
            self.client.images.remove('busybox:latest')  # pragma: no cover

        # Pull the image, which we now know we don't have.
        with self.assertLogs('seaworthy', level='INFO') as cm:
            dh.pull_image_if_not_found('busybox:latest')
        self.assertEqual(
            [l.getMessage() for l in cm.records],
            ["Pulling tag 'busybox:latest'..."])

        # Pull the image again, now that we know it's present.
        with self.assertLogs('seaworthy', level='DEBUG') as cm:
            dh.pull_image_if_not_found('busybox:latest')
        logs = [l.getMessage() for l in cm.records]
        self.assertEqual(len(logs), 1)
        self.assertRegex(
            logs[0],
            r"Found image 'sha256:[a-f0-9]{64}' for tag 'busybox:latest'")

    def test_namespace(self):
        """
        When the helper has its default namespace, the default network and all
        created containers should have names prefixed with the namespace.
        """
        dh = self.make_helper()

        network = dh.get_default_network()
        self.assertEqual(network.name, 'test_default')

        con = dh.create_container('con', IMG)
        self.addCleanup(dh.remove_container, con)
        self.assertEqual(con.name, 'test_con')

    def test_custom_namespace(self):
        """
        When the helper has a custom namespace, the default network and all
        created containers should have names prefixed with the namespace.
        """
        dh = self.make_helper(namespace='integ')

        network = dh.get_default_network()
        self.assertEqual(network.name, 'integ_default')

        con = dh.create_container('con', IMG)
        self.addCleanup(dh.remove_container, con)
        self.assertEqual(con.name, 'integ_con')
