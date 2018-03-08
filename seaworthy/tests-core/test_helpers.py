import tempfile
import unittest

import docker
from docker import models

from seaworthy.checks import docker_client, dockertest
from seaworthy.helpers import (
    ContainerHelper, DockerHelper, ImageHelper, NetworkHelper, VolumeHelper,
    _parse_image_tag, fetch_images)


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


# This is a private function but it's difficult to test indirectly without
# pulling images.
class TestParseImageTagFunc(unittest.TestCase):
    def test_with_tag(self):
        """An image name with a tag is parsed into a name and tag."""
        self.assertEqual(('test', 'foo'), _parse_image_tag('test:foo'))

    def test_without_tag(self):
        """An image name without a tag is parsed into a name and None."""
        self.assertEqual(('test', None), _parse_image_tag('test'))

    def test_with_tag_and_registry(self):
        """
        An image name with a tag and a registry is parsed into a name and tag.
        """
        self.assertEqual(('myregistry:5000/test', 'foo'),
                         _parse_image_tag('myregistry:5000/test:foo'))

    def test_without_tag_with_registry(self):
        """
        An image name without a tag but with a registry is parsed into a name
        and None.
        """
        self.assertEqual(('myregistry:5000/test', None),
                         _parse_image_tag('myregistry:5000/test'))


@dockertest()
class TestImageHelper(unittest.TestCase):
    def setUp(self):
        self.client = docker.client.from_env()
        self.addCleanup(self.client.api.close)

    def make_helper(self):
        return ImageHelper(self.client)

    def test_fetch(self):
        """
        We check if the image is already present and pull it if necessary.
        """
        ih = self.make_helper()

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
            ih.fetch('busybox:latest')
        self.assertEqual(
            [l.getMessage() for l in cm.records],
            ["Pulling tag 'latest' for image 'busybox'..."])

        # Pull the image again, now that we know it's present.
        with self.assertLogs('seaworthy', level='DEBUG') as cm:
            ih.fetch('busybox:latest')
        logs = [l.getMessage() for l in cm.records]
        self.assertEqual(len(logs), 1)
        self.assertRegex(
            logs[0],
            r"Found image 'sha256:[a-f0-9]{64}' for tag 'busybox:latest'")


@dockertest()
class TestNetworkHelper(unittest.TestCase):
    def setUp(self):
        self.client = docker.client.from_env()
        self.addCleanup(self.client.api.close)

    def make_helper(self, namespace='test'):
        nh = NetworkHelper(self.client, namespace)
        self.addCleanup(nh._teardown)
        return nh

    def list_networks(self, *args, namespace='test', **kw):
        return filter_by_name(
            self.client.networks.list(*args, **kw), '{}_'.format(namespace))

    def test_default_lifecycle(self):
        """
        The default network can only be created once and is removed during
        teardown.
        """
        nh = self.make_helper()
        # The default network isn't created unless required
        network = nh.get_default(create=False)
        self.assertIsNone(network)

        # Create the default network
        network = nh.get_default(create=True)
        self.assertIsNotNone(network)

        # We can try to get the network lots of times and we get the same one
        # and new ones aren't created.
        nh.get_default(create=False)
        nh.get_default(create=True)
        networks = self.list_networks()
        self.assertEqual(networks, [network])

        # The default network is removed on teardown
        nh._teardown()
        network = nh.get_default(create=False)
        self.assertIsNone(network)

    def test_default_already_exists(self):
        """
        If the default network already exists when we try to create it, we
        fail.
        """
        # We use a separate NetworkHelper (with the usual cleanup) to create
        # the test network so that the DockerHelper under test will see that it
        # already exists.
        nh1 = self.make_helper()
        nh1.get_default()
        # Now for the test.
        nh2 = self.make_helper()
        with self.assertRaises(docker.errors.APIError) as cm:
            nh2.get_default()
        self.assertIn('network', str(cm.exception))
        self.assertIn('already exists', str(cm.exception))

    def test_teardown(self):
        """
        NetworkHelper._teardown() will remove any networks that were created,
        even if they no longer exist.
        """
        nh = self.make_helper()
        self.assertEqual([], self.list_networks())
        net_bridge1 = nh.create('bridge1', driver='bridge')
        net_bridge2 = nh.create('bridge2', driver='bridge')

        net_removed = nh.create('removed')
        # We remove this behind the helper's back so the helper thinks it still
        # exists at teardown time.
        net_removed.remove()
        with self.assertRaises(docker.errors.NotFound):
            net_removed.reload()

        self.assertEqual(
            set([net_bridge1, net_bridge2]),
            set(self.list_networks()))

        with self.assertLogs('seaworthy', level='WARNING') as cm:
            nh._teardown()
        self.assertEqual(sorted(l.getMessage() for l in cm.records), [
            "Network 'test_bridge1' still existed during teardown",
            "Network 'test_bridge2' still existed during teardown",
        ])
        self.assertEqual([], self.list_networks())

    def test_create(self):
        """
        We can create a network with various parameters.
        """
        nh = self.make_helper()

        net_simple = nh.create('simple')
        self.addCleanup(nh.remove, net_simple)
        self.assertEqual(net_simple.name, 'test_simple')
        self.assertEqual(net_simple.attrs['Driver'], 'bridge')
        self.assertEqual(net_simple.attrs['Internal'], False)

        net_internal = nh.create('internal', internal=True)
        self.addCleanup(nh.remove, net_internal)
        self.assertEqual(net_internal.name, 'test_internal')
        self.assertEqual(net_internal.attrs['Internal'], True)

        # Copy custom IPAM/subnet example from Docker docs:
        # https://docker-py.readthedocs.io/en/2.5.1/networks.html#docker.models.networks.NetworkCollection.create
        ipam_pool = docker.types.IPAMPool(
            subnet='192.168.52.0/24', gateway='192.168.52.254')
        ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])
        net_subnet = nh.create('subnet', ipam=ipam_config)
        self.addCleanup(nh.remove, net_subnet)
        self.assertEqual(net_subnet.name, 'test_subnet')
        config = net_subnet.attrs['IPAM']['Config'][0]
        self.assertEqual(config['Subnet'], '192.168.52.0/24')
        self.assertEqual(config['Gateway'], '192.168.52.254')

    def test_remove(self):
        """
        We can remove a network.
        """
        nh = self.make_helper()

        net_test = nh.create('test')
        nh.remove(net_test)
        with self.assertRaises(docker.errors.NotFound):
            net_test.reload()

    def test_custom_namespace(self):
        """
        When the helper has a custom namespace, the networks created are
        prefixed with the namespace.
        """
        nh = self.make_helper(namespace='integ')

        net = nh.create('net')
        self.addCleanup(nh.remove, net)
        self.assertEqual(net.name, 'integ_net')


@dockertest()
class TestVolumeHelper(unittest.TestCase):
    def setUp(self):
        self.client = docker.client.from_env()
        self.addCleanup(self.client.api.close)

    def make_helper(self, namespace='test'):
        vh = VolumeHelper(self.client, namespace)
        self.addCleanup(vh._teardown)
        return vh

    def list_volumes(self, *args, namespace='test', **kw):
        return filter_by_name(
            self.client.volumes.list(*args, **kw), '{}_'.format(namespace))

    def test_teardown(self):
        """
        VolumeHelper._teardown() will remove any volumes that were created,
        even if they no longer exist.
        """
        vh = self.make_helper()
        self.assertEqual([], self.list_volumes())
        vol_local1 = vh.create('local1', driver='local')
        vol_local2 = vh.create('local2', driver='local')

        vol_removed = vh.create('removed')
        # We remove this behind the helper's back so the helper thinks it still
        # exists at teardown time.
        vol_removed.remove()
        with self.assertRaises(docker.errors.NotFound):
            vol_removed.reload()

        self.assertEqual(
            set([vol_local1, vol_local2]),
            set(self.list_volumes()))

        with self.assertLogs('seaworthy', level='WARNING') as cm:
            vh._teardown()
        self.assertEqual(sorted(l.getMessage() for l in cm.records), [
            "Volume 'test_local1' still existed during teardown",
            "Volume 'test_local2' still existed during teardown",
        ])
        self.assertEqual([], self.list_volumes())

    def test_create(self):
        """
        We can create a volume with various parameters.
        """
        vh = self.make_helper()

        vol_simple = vh.create('simple')
        self.addCleanup(vh.remove, vol_simple)
        self.assertEqual(vol_simple.name, 'test_simple')
        self.assertEqual(vol_simple.attrs['Driver'], 'local')

        vol_labels = vh.create('labels', labels={'foo': 'bar'})
        self.addCleanup(vh.remove, vol_labels)
        self.assertEqual(vol_labels.name, 'test_labels')
        self.assertEqual(vol_labels.attrs['Labels'], {'foo': 'bar'})

        # Copy tmpfs example from Docker docs:
        # https://docs.docker.com/engine/reference/commandline/volume_create/#driver-specific-options
        # This won't work on Windows
        driver_opts = {
            'type': 'tmpfs', 'device': 'tmpfs', 'o': 'size=100m,uid=1000'}
        vol_opts = vh.create('opts', driver='local', driver_opts=driver_opts)
        self.addCleanup(vh.remove, vol_opts)
        self.assertEqual(vol_opts.name, 'test_opts')
        self.assertEqual(vol_opts.attrs['Options'], driver_opts)

    def test_remove(self):
        """
        We can remove a volume.
        """
        vh = self.make_helper()

        vol_test = vh.create('test')
        vh.remove(vol_test)
        with self.assertRaises(docker.errors.NotFound):
            vol_test.reload()

    def test_custom_namespace(self):
        """
        When the helper has a custom namespace, the volumes created are
        prefixed with the namespace.
        """
        vh = self.make_helper(namespace='integ')

        vol = vh.create('vol')
        self.addCleanup(vh.remove, vol)
        self.assertEqual(vol.name, 'integ_vol')


@dockertest()
class TestContainerHelper(unittest.TestCase):
    def setUp(self):
        self.client = docker.client.from_env()
        self.addCleanup(self.client.api.close)

        self.ih = ImageHelper(self.client)
        self.nh = NetworkHelper(self.client, 'test')
        self.addCleanup(self.nh._teardown)
        self.vh = VolumeHelper(self.client, 'test')
        self.addCleanup(self.vh._teardown)

    def make_helper(self, namespace='test'):
        ch = ContainerHelper(self.client, namespace, self.ih, self.nh, self.vh)
        self.addCleanup(ch._teardown)
        return ch

    def list_containers(self, *args, namespace='test', **kw):
        return filter_by_name(
            self.client.containers.list(*args, **kw), '{}_'.format(namespace))

    def test_teardown(self):
        """
        ContainerHelper._teardown() will remove any containers that were
        created, no matter what state they are in or even whether they still
        exist.
        """
        ch = self.make_helper()
        self.assertEqual([], self.list_containers(all=True))
        con_created = ch.create('created', IMG)
        self.assertEqual(con_created.status, 'created')

        con_running = ch.create('running', IMG)
        con_running.start()
        con_running.reload()
        self.assertEqual(con_running.status, 'running')

        con_stopped = ch.create('stopped', IMG)
        con_stopped.start()
        con_stopped.reload()
        self.assertEqual(con_stopped.status, 'running')
        con_stopped.stop()
        con_stopped.reload()
        self.assertNotEqual(con_stopped.status, 'running')

        con_removed = ch.create('removed', IMG)
        # We remove this behind the helper's back so the helper thinks it still
        # exists at teardown time.
        con_removed.remove()
        with self.assertRaises(docker.errors.NotFound):
            con_removed.reload()

        self.assertEqual(
            set([con_created, con_running, con_stopped]),
            set(self.list_containers(all=True)))

        with self.assertLogs('seaworthy', level='WARNING') as cm:
            ch._teardown()
        self.assertEqual(sorted(l.getMessage() for l in cm.records), [
            "Container 'test_created' still existed during teardown",
            "Container 'test_running' still existed during teardown",
            "Container 'test_stopped' still existed during teardown",
        ])
        self.assertEqual([], self.list_containers(all=True))

    def test_create(self):
        """
        We can create a container with various parameters without starting it.
        """
        ch = self.make_helper()

        con_simple = ch.create('simple', IMG)
        self.addCleanup(ch.remove, con_simple)
        self.assertEqual(con_simple.status, 'created')
        self.assertEqual(con_simple.attrs['Path'], 'nginx')

        con_cmd = ch.create('cmd', IMG, command='echo hello')
        self.addCleanup(ch.remove, con_cmd)
        self.assertEqual(con_cmd.status, 'created')
        self.assertEqual(con_cmd.attrs['Path'], 'echo')

        con_env = ch.create('env', IMG, environment={'FOO': 'bar'})
        self.addCleanup(ch.remove, con_env)
        self.assertEqual(con_env.status, 'created')
        self.assertIn('FOO=bar', con_env.attrs['Config']['Env'])

    def test_network(self):
        """
        When a container is created, the network settings are respected, and if
        no network settings are specified, the container is connected to a
        default network.
        """
        ch = self.make_helper()

        # When 'network' is provided, that network is used
        custom_network = self.nh.create('network')
        self.addCleanup(self.nh.remove, custom_network)
        con_network = ch.create('network', IMG, network=custom_network)
        self.addCleanup(ch.remove, con_network)
        networks = con_network.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [custom_network.name])
        network = networks[custom_network.name]
        self.assertCountEqual(
            network['Aliases'], [con_network.id[:12], 'network'])

        # When 'network_mode' is provided, the default network is not used
        con_mode = ch.create('mode', IMG, network_mode='none')
        self.addCleanup(ch.remove, con_mode)
        networks = con_mode.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), ['none'])

        # When 'network_disabled' is True, the default network is not used
        con_disabled = ch.create(
            'disabled', IMG, network_disabled=True)
        self.addCleanup(ch.remove, con_disabled)
        self.assertEqual(con_disabled.attrs['NetworkSettings']['Networks'], {})

        con_default = ch.create('default', IMG)
        self.addCleanup(ch.remove, con_default)
        default_network_name = self.nh.get_default().name
        networks = con_default.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [default_network_name])
        network = networks[default_network_name]
        self.assertCountEqual(
            network['Aliases'], [con_default.id[:12], 'default'])

    def test_network_by_id(self):
        """
        When a container is created, a network can be specified using the ID
        string for a network.
        """
        ch = self.make_helper()

        # When 'network' is provided as an ID, that network is used
        net_id = self.nh.create('id')
        self.addCleanup(self.nh.remove, net_id)
        con_id = ch.create('id', IMG, network=net_id.id)
        self.addCleanup(ch.remove, con_id)
        networks = con_id.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_id.name])
        network = networks[net_id.name]
        self.assertCountEqual(network['Aliases'], [con_id.id[:12], 'id'])

    def test_network_by_short_id(self):
        """
        When a container is created, a network can be specified using the short
        ID string for a network.
        """
        ch = self.make_helper()

        # When 'network' is provided as a short ID, that network is used
        net_short_id = self.nh.create('short_id')
        self.addCleanup(self.nh.remove, net_short_id)
        con_short_id = ch.create(
            'short_id', IMG, network=net_short_id.short_id)
        self.addCleanup(ch.remove, con_short_id)
        networks = con_short_id.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_short_id.name])
        network = networks[net_short_id.name]
        self.assertCountEqual(
            network['Aliases'], [con_short_id.id[:12], 'short_id'])

    def test_network_by_name(self):
        """
        When a container is created, a network can be specified using the name
        of a network.
        """
        ch = self.make_helper()

        # When 'network' is provided as a name, that network is used
        net_name = self.nh.create('name')
        self.addCleanup(self.nh.remove, net_name)
        con_name = ch.create('name', IMG, network=net_name.name)
        self.addCleanup(ch.remove, con_name)
        networks = con_name.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_name.name])
        network = networks[net_name.name]
        self.assertCountEqual(network['Aliases'], [con_name.id[:12], 'name'])

    def test_network_by_invalid_type(self):
        """
        When a container is created, an error is raised if a network is
        specified using an invalid type.
        """
        ch = self.make_helper()

        with self.assertRaises(TypeError) as cm:
            ch.create('invalid_type', IMG, network=42)

        self.assertEqual(
            str(cm.exception),
            "Unexpected type <class 'int'>, expected <class 'str'> or <class "
            "'docker.models.networks.Network'>")

    def test_volumes(self):
        """
        When a container is created, a volume can be specified to be mounted.
        The container metadata should correctly identify the volumes and its
        mountpoint.
        """
        ch = self.make_helper()

        vol_test = self.vh.create('test')
        self.addCleanup(self.vh.remove, vol_test)
        con_volumes = ch.create(
            'volumes', IMG, volumes={vol_test: {'bind': '/vol', 'mode': 'rw'}})
        self.addCleanup(ch.remove, con_volumes)
        mounts = con_volumes.attrs['Mounts']
        self.assertEqual(len(mounts), 1)
        [mount] = mounts
        self.assertEqual(mount['Type'], 'volume')
        self.assertEqual(mount['Name'], vol_test.name)
        self.assertEqual(mount['Source'], vol_test.attrs['Mountpoint'])
        self.assertEqual(mount['Driver'], vol_test.attrs['Driver'])
        self.assertEqual(mount['Destination'], '/vol')
        self.assertEqual(mount['Mode'], 'rw')

    def test_volumes_short_form(self):
        """
        When a container is created, a volume can be specified to be mounted
        using a short-form bind specfier. The mode can be specified, but if not
        it defaults to read/write.
        """
        ch = self.make_helper()

        # Default mode: rw
        vol_default = self.vh.create('default')
        self.addCleanup(self.vh.remove, vol_default)
        con_default = ch.create('default', IMG, volumes={vol_default: '/vol'})
        self.addCleanup(ch.remove, con_default)
        mounts = con_default.attrs['Mounts']
        self.assertEqual(len(mounts), 1)
        [mount] = mounts
        self.assertEqual(mount['Type'], 'volume')
        self.assertEqual(mount['Name'], vol_default.name)
        self.assertEqual(mount['Destination'], '/vol')
        self.assertEqual(mount['Mode'], 'rw')

        # Specific mode: ro
        vol_mode = self.vh.create('mode')
        self.addCleanup(self.vh.remove, vol_mode)
        con_mode = ch.create('mode', IMG, volumes={vol_mode: '/mnt:ro'})
        self.addCleanup(ch.remove, con_mode)
        mounts = con_mode.attrs['Mounts']
        self.assertEqual(len(mounts), 1)
        [mount] = mounts
        self.assertEqual(mount['Type'], 'volume')
        self.assertEqual(mount['Name'], vol_mode.name)
        self.assertEqual(mount['Destination'], '/mnt')
        self.assertEqual(mount['Mode'], 'ro')

    def test_volumes_bind(self):
        """
        When a container is created, a bind mount can be specified in the
        ``volumes`` hash. The container metadata should correctly describe the
        bind mount.
        """
        ch = self.make_helper()

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        con_bind = ch.create(
            'bind', IMG, volumes={tmpdir.name: {'bind': '/vol', 'mode': 'rw'}})
        self.addCleanup(ch.remove, con_bind)
        mounts = con_bind.attrs['Mounts']
        self.assertEqual(len(mounts), 1)
        [mount] = mounts
        self.assertEqual(mount['Type'], 'bind')
        self.assertEqual(mount['Source'], tmpdir.name)
        self.assertEqual(mount['Destination'], '/vol')
        self.assertTrue(mount['RW'])

    def test_volumes_by_name(self):
        """
        When a container is created, volumes can be specified using volume
        names. Volumes don't have IDs, only names :-/
        """
        ch = self.make_helper()

        # When 'volumes' is provided as a mapping from names, those volumes are
        # used
        vol_name = self.vh.create('name')
        self.addCleanup(self.vh.remove, vol_name)
        con_name = ch.create(
            'name', IMG,
            volumes={vol_name.name: {'bind': '/vol', 'mode': 'rw'}})
        self.addCleanup(ch.remove, con_name)
        mounts = con_name.attrs['Mounts']
        self.assertEqual(len(mounts), 1)
        [mount] = mounts
        self.assertEqual(mount['Name'], vol_name.name)

    def test_volumes_by_invalid_type(self):
        """
        When a container is created, an error is raised if a volume is
        specified using an invalid type.
        """
        ch = self.make_helper()

        with self.assertRaises(TypeError) as cm:
            ch.create('invalid_type', IMG,
                      volumes={42: {'bind': '/vol', 'mode': 'rw'}})

        self.assertEqual(
            str(cm.exception),
            "Unexpected type <class 'int'>, expected <class 'str'> or <class "
            "'docker.models.volumes.Volume'>")

    def test_volumes_specified_twice(self):
        """
        When a container is created, an error is raised if the same volume is
        specified twice: once using its string ID, and once using its model
        object.
        """
        ch = self.make_helper()

        # When 'volumes' is provided as a mapping from names, those volumes are
        # used
        vol_duplicate = self.vh.create('duplicate')
        self.addCleanup(self.vh.remove, vol_duplicate)
        with self.assertRaises(ValueError) as cm:
            ch.create(
                'duplicate', IMG,
                volumes={
                    vol_duplicate.name: {'bind': '/vol', 'mode': 'rw'},
                    vol_duplicate: {'bind': '/vol2', 'mode': 'ro'},
                })

        self.assertEqual(str(cm.exception),
                         "Volume 'test_duplicate' specified more than once")

    def test_remove(self):
        """
        We can remove a not-running container.
        """
        ch = self.make_helper()

        con_created = ch.create('created', IMG)
        self.assertEqual(con_created.status, 'created')
        ch.remove(con_created)
        with self.assertRaises(docker.errors.NotFound):
            con_created.reload()

        con_stopped = ch.create('stopped', IMG)
        con_stopped.start()
        con_stopped.stop()
        con_stopped.reload()
        self.assertEqual(con_stopped.status, 'exited')
        ch.remove(con_stopped)
        with self.assertRaises(docker.errors.NotFound):
            con_stopped.reload()

    def test_remove_force(self):
        """
        We can't remove a running container without forcing it.
        """
        ch = self.make_helper()

        con_running = ch.create('running', IMG)
        con_running.start()
        con_running.reload()
        self.assertEqual(con_running.status, 'running')
        with self.assertRaises(docker.errors.APIError):
            ch.remove(con_running, force=False)
        ch.remove(con_running)
        with self.assertRaises(docker.errors.NotFound):
            con_running.reload()

    def test_custom_namespace(self):
        """
        When the helper has a custom namespace, the containers created are
        prefixed with the namespace.
        """
        ch = self.make_helper(namespace='integ')

        con = ch.create('con', IMG, network_mode='none')
        self.addCleanup(ch.remove, con)
        self.assertEqual(con.name, 'integ_con')


@dockertest()
class TestDockerHelper(unittest.TestCase):
    def setUp(self):
        self.client = docker.client.from_env()
        self.addCleanup(self.client.api.close)

    def make_helper(self, *args, **kwargs):
        """
        Create and return a DockerHelper instance that will be cleaned up after
        the test.
        """
        dh = DockerHelper(*args, **kwargs)
        self.addCleanup(dh.teardown)
        return dh

    def test_custom_client(self):
        """
        When the DockerHelper is created with a custom client, that client is
        used.
        """
        client = docker.DockerClient(base_url='unix://var/run/docker.sock')
        dh = self.make_helper(client=client)

        self.assertIs(dh._client, client)

    def test_teardown_safe(self):
        """
        DockerHelper.teardown() is safe to call multiple times.

        There are no assertions here. We only care that calling teardown never
        raises any exceptions.
        """
        dh = self.make_helper()
        # These should silently do nothing.
        dh.teardown()
        dh.teardown()

    def test_remove_network_connected_to_created_container(self):
        """
        We can remove a network when it is connected to a container if the
        container hasn't been started yet.
        """
        dh = self.make_helper()

        net_test = dh.networks.create('test')

        con_created = dh.containers.create('created', IMG, network=net_test)
        self.addCleanup(dh.containers.remove, con_created)
        self.assertEqual(con_created.status, 'created')
        networks = con_created.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_test.name])

        # Container not yet started so not listed as container connected to
        # network
        net_test.reload()
        self.assertEqual(net_test.containers, [])

        # Container not yet started so we can remove the network
        dh.networks.remove(net_test)
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
        net_test = dh.networks.create('test')
        con_running = dh.containers.create('running', IMG, network=net_test)
        self.addCleanup(dh.containers.remove, con_running)
        networks = con_running.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_test.name])

        # Start the container, now the network should know about it
        con_running.start()
        con_running.reload()
        self.assertEqual(con_running.status, 'running')
        net_test.reload()
        self.assertEqual(net_test.containers, [con_running])

        with self.assertRaises(docker.errors.APIError) as cm:
            dh.networks.remove(net_test)
        self.assertIn('network', str(cm.exception))
        self.assertIn('has active endpoints', str(cm.exception))

        # Once the container is disconnected, the network can be removed
        net_test.disconnect(con_running)
        dh.networks.remove(net_test)

        with self.assertRaises(docker.errors.NotFound):
            net_test.reload()

    def test_remove_network_connected_to_stopped_container(self):
        """
        We can remove a network when it is connected to a container if the
        container has been stopped.
        """
        dh = self.make_helper()

        # Create a network and connect it to a container
        net_test = dh.networks.create('test')
        con_stopped = dh.containers.create('stopped', IMG, network=net_test)
        self.addCleanup(dh.containers.remove, con_stopped)
        networks = con_stopped.attrs['NetworkSettings']['Networks']
        self.assertEqual(list(networks.keys()), [net_test.name])

        # Stop the container
        con_stopped.start()
        con_stopped.stop()
        con_stopped.reload()
        self.assertEqual(con_stopped.status, 'exited')

        net_test.reload()
        self.assertEqual(net_test.containers, [])
        dh.networks.remove(net_test)

        with self.assertRaises(docker.errors.NotFound):
            net_test.reload()

    def test_cannot_remove_mounted_volume(self):
        """
        We can't remove a volume mounted to a container no matter what state
        the container is in. Once the container has been removed, we can remove
        the volume.
        """
        dh = self.make_helper()

        vol_created = dh.volumes.create('created')
        con_created = dh.containers.create(
            'created', IMG,
            volumes={vol_created: {'bind': '/vol', 'mode': 'rw'}})
        self.assertEqual(con_created.status, 'created')

        # Try remove the volume... we can't
        with self.assertRaises(docker.errors.APIError) as cm:
            dh.volumes.remove(vol_created)
        self.assertIn('volume is in use', str(cm.exception))

        # Remove the container and then the volume
        dh.containers.remove(con_created)
        dh.volumes.remove(vol_created)

        vol_running = dh.volumes.create('running')
        con_running = dh.containers.create(
            'running', IMG,
            volumes={vol_running: {'bind': '/vol', 'mode': 'rw'}})

        con_running.start()
        con_running.reload()
        self.assertEqual(con_running.status, 'running')

        # Try remove the volume... we can't
        with self.assertRaises(docker.errors.APIError) as cm:
            dh.volumes.remove(vol_running)
        self.assertIn('volume is in use', str(cm.exception))

        # Remove the container and then the volume
        dh.containers.remove(con_running)
        dh.volumes.remove(vol_running)

        vol_stopped = dh.volumes.create('stopped')
        con_stopped = dh.containers.create(
            'stopped', IMG,
            volumes={vol_stopped: {'bind': '/vol', 'mode': 'rw'}})

        con_stopped.start()
        con_stopped.stop()
        con_stopped.reload()
        self.assertEqual(con_stopped.status, 'exited')

        # Try remove the volume... we can't
        with self.assertRaises(docker.errors.APIError) as cm:
            dh.volumes.remove(vol_stopped)
        self.assertIn('volume is in use', str(cm.exception))

        # Remove the container and then the volume
        dh.containers.remove(con_stopped)
        dh.volumes.remove(vol_stopped)

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

        vol_test = dh.volumes.create('test')
        self.addCleanup(dh.volumes.remove, vol_test)
        con_created = dh.containers.create(
            'created', IMG, volumes={vol_test: {'bind': '/vol', 'mode': 'rw'}})
        self.addCleanup(dh.containers.remove, con_created)
        self.assertEqual(con_created.status, 'created')

        # Try remove the volume... we can't
        with self.assertRaises(docker.errors.APIError) as cm:
            dh.volumes.remove(vol_test, force=True)
        self.assertIn('volume is in use', str(cm.exception))

    def test_remove_container_with_volume(self):
        """
        When a volume is mounted to a container, and the container is removed,
        the volume itself is not removed.
        """
        dh = self.make_helper()

        vol_removed = dh.volumes.create('removed')
        self.addCleanup(dh.volumes.remove, vol_removed)
        con_removed = dh.containers.create(
            'removed', IMG,
            volumes={vol_removed: {'bind': '/vol', 'mode': 'rw'}})

        dh.containers.remove(con_removed)
        with self.assertRaises(docker.errors.NotFound):
            con_removed.reload()

        # The volume still exists: we can fetch it
        vol_removed.reload()

    def test_default_namespace(self):
        """
        When the Docker helper has the default namespace, all the resource
        helpers are created with that namespace.
        """
        dh = self.make_helper()
        self.assertEqual(dh.containers.namespace, 'test')
        self.assertEqual(dh.networks.namespace, 'test')
        self.assertEqual(dh.volumes.namespace, 'test')

    def test_custom_namespace(self):
        """
        When the Docker helper has a custom namespace, all the resource helpers
        are created with that namespace.
        """
        dh = self.make_helper(namespace='integ')
        self.assertEqual(dh.containers.namespace, 'integ')
        self.assertEqual(dh.networks.namespace, 'integ')
        self.assertEqual(dh.volumes.namespace, 'integ')

    def test_helper_for_model(self):
        """
        The _helper_for_model method returns the correct helper for the given
        Docker model type, or raises an exception if the model is of an unknown
        type.
        """
        dh = self.make_helper()
        self.assertIs(
            dh._helper_for_model(models.containers.Container), dh.containers)
        self.assertIs(dh._helper_for_model(models.images.Image), dh.images)
        self.assertIs(
            dh._helper_for_model(models.networks.Network), dh.networks)
        self.assertIs(dh._helper_for_model(models.volumes.Volume), dh.volumes)

        with self.assertRaises(ValueError) as cm:
            dh._helper_for_model(models.plugins.Plugin)
        self.assertEqual(
            str(cm.exception),
            "Unknown model type <class 'docker.models.plugins.Plugin'>")
