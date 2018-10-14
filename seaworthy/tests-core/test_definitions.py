import time
import unittest
from datetime import datetime

from seaworthy.checks import docker_client, dockertest
from seaworthy.definitions import (
    ContainerDefinition, NetworkDefinition, VolumeDefinition)
from seaworthy.helpers import DockerHelper, fetch_images
from seaworthy.stream.matchers import EqualsMatcher

IMG_SCRIPT = 'alpine:latest'
IMG_WAIT = 'nginx:alpine'


@dockertest()
class DefinitionTestMixin:
    def _setup(self):
        self.dh = DockerHelper()
        self.addCleanup(self.dh.teardown)

        self.definition = self.with_cleanup(
            self.make_definition('test', helper=self.dh))
        self.helper = self.definition.helper

    def with_cleanup(self, definition):
        self.addCleanup(definition.teardown)
        return definition

    def make_definition(self, name, helper=None):
        raise NotImplementedError()  # pragma: no cover

    def test_helper_not_set(self):
        """
        By default, we have no helper.
        """
        no_helper = self.make_definition('no_helper')
        self.assertIsNone(no_helper._helper)
        with self.assertRaises(RuntimeError) as cm:
            no_helper.helper
        self.assertEqual(str(cm.exception), 'No helper set.')

    def test_helper_set_in_constructor(self):
        """
        We can set a helper in the constructor.
        """
        with_helper = self.make_definition('with_helper', helper=self.helper)
        self.assertIs(with_helper._helper, self.helper)
        self.assertIs(with_helper.helper, self.helper)

    def test_helper_set_to_none(self):
        """
        Setting helper to None has no effect even if we already have
        one.
        """
        no_helper = self.make_definition('no_helper')
        self.assertIsNone(no_helper._helper)
        no_helper.set_helper(None)
        self.assertIsNone(no_helper._helper)

        with_helper = self.make_definition('with_helper', helper=self.helper)
        self.assertIs(with_helper._helper, self.helper)
        with_helper.set_helper(None)
        self.assertIs(with_helper._helper, self.helper)

    def test_helper_set_to_current(self):
        """
        Setting helper to the one we already have has no effect.
        """
        with_helper = self.make_definition('with_helper', helper=self.helper)
        self.assertIs(with_helper._helper, self.helper)
        with_helper.set_helper(self.helper)
        self.assertIs(with_helper._helper, self.helper)

    def test_cannot_replace_helper(self):
        """
        If we already have a helper, we can't set a different one.
        """
        with_helper = self.make_definition('with_helper', helper=self.helper)
        self.assertIs(with_helper.helper, self.helper)
        # TODO: fix this...
        with self.assertRaises(RuntimeError) as cm:
            with_helper.set_helper(DockerHelper())
        self.assertEqual(
            str(cm.exception), 'Cannot replace existing helper.')
        self.assertIs(with_helper.helper, self.helper)

    def test_helper_set_to_docker_helper(self):
        """
        Setting helper to a DockerHelper instance gets us the correct helper.
        """
        with_helper = self.make_definition('with_helper', helper=self.dh)
        self.assertIs(
            with_helper._helper.collection.model, with_helper.__model_type__)
        self.assertIs(with_helper._helper, self.helper)

    def test_create_only_if_not_created(self):
        """
        The resource cannot be created more than once.
        """
        self.definition.create()

        # We can't create the resource when it's already created
        with self.assertRaises(RuntimeError) as cm:
            self.definition.create()
        self.assertRegex(str(cm.exception), r'^\w+ already created\.$')

        self.definition.remove()

    def test_remove_only_if_created(self):
        """
        The resource can only be removed if it has been created.
        """
        self.definition.create()

        # We can remove the resource if it's created
        self.definition.remove()

        with self.assertRaises(RuntimeError) as cm:
            self.definition.remove()
        self.assertRegex(str(cm.exception), r'^\w+ not created yet\.$')

    def test_inner_only_if_created(self):
        """
        We can only access the inner object if the resource has been
        created.
        """
        # If we try get the resource before it's created it'll fail
        with self.assertRaises(RuntimeError) as cm:
            self.definition.inner()
        self.assertRegex(str(cm.exception), r'^\w+ not created yet\.$')

        self.definition.create()

        # We can get the resource once it's created
        inner = self.definition.inner()
        self.assertIsInstance(inner, self.definition.__model_type__)

        self.definition.remove()
        with self.assertRaises(RuntimeError) as cm:
            self.definition.inner()
        self.assertRegex(str(cm.exception), r'^\w+ not created yet\.$')

    def test_setup_teardown(self):
        """
        We can use the ``setup`` and ``teardown`` methods to create and remove
        the resource.
        """
        self.assertFalse(self.definition.created)

        self.definition.setup()
        self.assertTrue(self.definition.created)

        self.definition.teardown()
        self.assertFalse(self.definition.created)

    def test_setup_kwargs(self):
        """
        We can pass keyword args to ``setup``.
        """
        self.assertFalse(self.definition.created)

        self.definition.setup(labels={'SETUP_KWARGS': 'working'})
        self.addCleanup(self.definition.teardown)
        self.assertTrue(self.definition.created)
        labels = self.definition.inner().attrs['Labels']
        self.assertEqual(labels, {'SETUP_KWARGS': 'working'})

    def test_setup_multiple_calls(self):
        """
        setup() can be called multiple times after it has been called once
        without having any effect.
        """
        self.assertFalse(self.definition.created)

        self.definition.setup()
        self.assertTrue(self.definition.created)
        inner = self.definition.inner()

        self.definition.setup()
        self.definition.setup()

        self.assertIs(inner, self.definition.inner())

    def test_teardown_multiple_calls(self):
        """
        teardown() can be called multiple times after it has been called once
        without having any effect.
        """
        self.assertFalse(self.definition.created)
        self.definition.setup()
        self.assertTrue(self.definition.created)

        self.definition.teardown()
        self.assertFalse(self.definition.created)

        self.definition.teardown()
        self.definition.teardown()

    def test_context_manager(self):
        """
        We can use a definition object as a context manager (which returns
        itself) to create and remove it.
        """
        self.assertFalse(self.definition.created)
        with self.definition as definition:
            self.assertIs(definition, self.definition)
            self.assertTrue(definition.created)
        self.assertFalse(self.definition.created)

    def test_fixture_on_function(self):
        """
        We can make a function decorator fixture for our definition.
        """
        self.assertFalse(self.definition.created)
        closure_state = []

        @self.definition.as_fixture()
        def foo(test):
            self.assertIs(test, self.definition)
            self.assertTrue(self.definition.created)
            closure_state.append(1)

        self.assertEqual(closure_state, [])
        self.assertFalse(self.definition.created)
        foo()
        self.assertFalse(self.definition.created)
        self.assertEqual(closure_state, [1])

    def test_fixture_on_method(self):
        """
        The fixture decorator works on methods too.
        """
        self.assertFalse(self.definition.created)
        closure_state = []

        class Foo:
            def __init__(self, value, tc):
                self.value = value
                self.tc = tc

            @self.definition.as_fixture()
            def foo(self, test):
                self.tc.assertIs(test, self.tc.definition)
                self.tc.assertTrue(test.created)
                closure_state.append(self.value)

        self.assertEqual(closure_state, [])
        self.assertFalse(self.definition.created)
        Foo(3, self).foo()
        self.assertFalse(self.definition.created)
        self.assertEqual(closure_state, [3])

    def test_fixture_with_name(self):
        """
        The fixture decorator can override the parameter name used.
        """
        self.assertFalse(self.definition.created)
        closure_state = []

        @self.definition.as_fixture(name='something_more_sensible')
        def foo(something_more_sensible):
            self.assertIs(something_more_sensible, self.definition)
            self.assertTrue(something_more_sensible.created)
            closure_state.append(1)

        self.assertEqual(closure_state, [])
        self.assertFalse(self.definition.created)
        foo()
        self.assertFalse(self.definition.created)
        self.assertEqual(closure_state, [1])

    def test_merge_kwargs(self):
        """
        The default merge_kwargs() method deep-merges the two kwargs dicts
        passed to it.
        """
        create_kwargs = {'a': {'aa': 1, 'ab': 2}, 's': 'foo', 't': 'bar'}
        kwargs = {'a': {'ba': 3, 'ab': 4}, 'r': 'arr', 't': 'baz'}
        self.assertEqual(self.definition.merge_kwargs(create_kwargs, kwargs), {
            'a': {'aa': 1, 'ab': 4, 'ba': 3},
            'r': 'arr',
            's': 'foo',
            't': 'baz',
        })

    def test_merge_kwargs_with_base(self):
        """
        The default merge_kwargs() method deep-merges the two kwargs dicts
        passed to it on top of the output of base_kwargs().
        """
        self.definition.base_kwargs = (
            lambda: {'a': {'aa': 0, 'bb': 6}, 'b': 'base'})
        create_kwargs = {'a': {'aa': 1, 'ab': 2}, 's': 'foo', 't': 'bar'}
        kwargs = {'a': {'ba': 3, 'ab': 4}, 'r': 'arr', 't': 'baz'}
        self.assertEqual(self.definition.merge_kwargs(create_kwargs, kwargs), {
            'a': {'aa': 1, 'ab': 4, 'ba': 3, 'bb': 6},
            'b': 'base',
            'r': 'arr',
            's': 'foo',
            't': 'baz',
        })

    def test_merge_kwargs_dicts_only(self):
        """
        The kwargs we merge must be dicts.
        """
        with self.assertRaises(Exception):
            self.definition.merge_kwargs({}, 'hello')
        with self.assertRaises(Exception):
            self.definition.merge_kwargs('hello', {})


@dockertest()
class TestContainerDefinition(unittest.TestCase, DefinitionTestMixin):
    @classmethod
    def setUpClass(cls):
        with docker_client() as client:
            fetch_images(client, [IMG_SCRIPT, IMG_WAIT])

    def setUp(self):
        self._setup()

    def make_definition(self, name, helper=None):
        return ContainerDefinition(name, IMG_WAIT, helper=helper)

    def test_setup_teardown(self):
        """
        We can use the ``setup`` and ``teardown`` methods to create and remove
        the container.
        """
        self.assertFalse(self.definition.created)

        self.definition.setup()
        self.assertTrue(self.definition.created)
        # Also assert that the container is running
        self.assertEqual(self.definition.status(), 'running')

        self.definition.teardown()
        self.assertFalse(self.definition.created)
        # No status for container now
        self.assertIs(self.definition.status(), None)

    def test_setup_kwargs(self):
        """
        We can pass keyword args to ``setup``.
        """
        self.assertFalse(self.definition.created)

        self.definition.setup(environment={'SETUP_KWARGS': 'working'})
        self.addCleanup(self.definition.teardown)
        self.assertTrue(self.definition.created)
        env = self.definition.inner().attrs['Config']['Env']
        self.assertIn('SETUP_KWARGS=working', env)

    def test_context_manager(self):
        """
        We can use a definition object as a context manager (which returns
        itself) to create and remove it.
        """
        self.assertFalse(self.definition.created)
        with self.definition as definition:
            self.assertIs(definition, self.definition)
            self.assertTrue(definition.created)
            # Also assert that the container is running
            self.assertEqual(definition.status(), 'running')
        self.assertFalse(self.definition.created)
        # No status for container now
        self.assertIs(self.definition.status(), None)

    def test_start(self):
        """
        We can start a container after creating it.
        """
        self.definition.create()
        inner = self.definition.inner()
        self.assertEqual(inner.status, 'created')

        self.definition.start()
        self.assertEqual(inner.status, 'running')

    def test_stop(self):
        """
        We can stop a running container.
        """
        # We don't test the timeout because that's just passed directly through
        # to Docker and it's nontrivial to construct a container that takes a
        # specific amount of time to stop.
        self.definition.create()
        inner = self.definition.inner()
        self.assertEqual(inner.status, 'created')

        self.definition.start()
        self.assertEqual(inner.status, 'running')

        self.definition.stop()
        self.assertEqual(inner.status, 'exited')

    def test_wait_timeout_default(self):
        """
        When wait_timeout isn't passed to the constructor, the default timeout
        is used.
        """
        container = ContainerDefinition('timeout', IMG_WAIT)
        self.assertEqual(
            container.wait_timeout, ContainerDefinition.WAIT_TIMEOUT)

    def test_wait_timeout_override(self):
        """
        When wait_timeout is passed to the constructor, it is used in place of
        the default.
        """
        timeout = ContainerDefinition.WAIT_TIMEOUT + 10.0
        container = ContainerDefinition(
            'timeout', IMG_WAIT, wait_timeout=timeout)
        self.assertEqual(container.wait_timeout, timeout)

    def test_default_clean(self):
        """By default, the ``clean`` method raises a NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.definition.clean()

    def test_create_kwargs_handling(self):
        """
        The keyword args passed used for container creation come from the
        return value of merge_kwargs() called on create_kwargs from the
        constructor and kwargs from the create() method.
        """
        create_kwargs = {
            'environment': {'CREATE_KWARGS': 't', 'KWARGS_MERGED': 'f'},
        }
        kwargs = {'environment': {'KWARGS': 't', 'KWARGS_MERGED': 't'}}
        merge_kwargs_args = []

        class SubContainer(ContainerDefinition):
            def merge_kwargs(self, *args):
                merge_kwargs_args.extend(args)
                return super().merge_kwargs(*args)

        c = self.with_cleanup(SubContainer(
            'kwargs', IMG_WAIT, create_kwargs=create_kwargs,
            helper=self.helper))
        c.create(**kwargs)

        self.assertEqual(merge_kwargs_args, [create_kwargs, kwargs])
        c_env = [v for v in c.inner().attrs['Config']['Env'] if 'KWARGS' in v]
        self.assertEqual(
            sorted(c_env), ['CREATE_KWARGS=t', 'KWARGS=t', 'KWARGS_MERGED=t'])

    def test_ports(self):
        """
        We can get the ports exposed or published on a container.
        """
        self.definition.run(
            fetch_image=False, ports={'8000/tcp': ('127.0.0.1', '10701')})

        # We're not interested in the order of the ports
        self.assertCountEqual(self.definition.ports.items(), [
            ('80/tcp', None),
            ('8000/tcp', [{'HostIp': '127.0.0.1', 'HostPort': '10701'}]),
        ])

    def test_get_host_port(self):
        """
        We can get the host port mapping of a container.
        """
        self.definition.run(fetch_image=False, ports={
            '8080/tcp': ('127.0.0.1',),
            '9090/tcp': ('127.0.0.1', '10701'),
            '9191/udp': '10702',
        })

        # We get a random high port number here.
        host_iface, random_host_port = self.definition.get_host_port('8080')
        self.assertEqual(host_iface, '127.0.0.1')
        self.assertGreater(int(random_host_port), 1024)
        self.assertLess(int(random_host_port), 65536)

        # We get the specific port we defined here.
        host_iface, specific_host_port = self.definition.get_host_port('9090')
        self.assertEqual(host_iface, '127.0.0.1')
        self.assertEqual(specific_host_port, '10701')

        # We get a UDP port we defined.
        _, udp_host_port = self.definition.get_host_port('9191', proto='udp')
        self.assertEqual(udp_host_port, '10702')

        # FIXME: Don't bother testing index != 0, the port order is
        # unpredictable :-(

    def test_get_host_port_not_exposed(self):
        """
        When we try to get the host port for a container port that hasn't been
        exposed, an error is raised.
        """
        self.definition.run(
            fetch_image=False, ports={'8000/tcp': ('127.0.0.1', '10701')})

        self.assertNotIn('90/tcp', self.definition.ports)

        with self.assertRaises(ValueError) as cm:
            self.definition.get_host_port('90')
        self.assertEqual(str(cm.exception), "Port '90/tcp' is not exposed")

    def test_get_host_port_not_published(self):
        """
        When we try to get the host port for a container port that hasn't been
        published to the host, an error is raised.
        """
        self.definition.run(
            fetch_image=False, ports={'8000/tcp': ('127.0.0.1', '10701')})

        # The Nginx image EXPOSEs port 80, but we don't publish it
        self.assertIn('80/tcp', self.definition.ports)

        with self.assertRaises(ValueError) as cm:
            self.definition.get_host_port('80')
        self.assertEqual(
            str(cm.exception), "Port '80/tcp' is not published to the host")

    def test_get_first_host_port(self):
        """
        When we get the first host port for the container, the host port mapped
        to the lowest container port is returned.
        """
        self.definition.run(
            fetch_image=False, ports={
                '8000/tcp': ('127.0.0.1',),
                '90/tcp': ('127.0.0.1', '10701'),
                '90/udp': ('127.0.0.1', '10702'),
            })

        # The Nginx image EXPOSEs port 80, but it's not published so shouldn't
        # be considered by ``get_first_host_port()``
        self.assertIn('80/tcp', self.definition.ports)

        host_iface, host_port = self.definition.get_first_host_port()
        self.assertEqual(host_iface, '127.0.0.1')
        self.assertEqual(host_port, '10701')

    def test_get_first_host_port_no_mappings(self):
        """
        When we try to get the first host port, but the container has no
        published ports, an error is raised.
        """
        self.definition.run(fetch_image=False)

        # The Nginx image EXPOSEs port 80, but it's not published so shouldn't
        # be considered by ``get_first_host_port()``
        self.assertIn('80/tcp', self.definition.ports)

        with self.assertRaises(RuntimeError) as cm:
            self.definition.get_first_host_port()

        self.assertEqual(str(cm.exception), 'Container has no published ports')

    def run_logs_container(self, logs, wait=True, delay=0.01):
        # Sleep some amount between lines to ensure ordering across stdout and
        # stderr.
        script = '\nsleep {}\n'.format(delay).join(logs)

        script_con = self.with_cleanup(
            ContainerDefinition('script', IMG_SCRIPT, helper=self.helper))

        script_con.run(fetch_image=False, command=['sh', '-c', script])
        # Wait for the output to arrive.
        if wait:
            # Wait a minimum of 100ms to avoid jitter with small intervals.
            time.sleep(max(0.1, len(logs) * delay))
        return script_con

    def test_get_logs_out_err(self):
        """
        We can choose stdout and/or stderr when getting logs from a container.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ])

        self.assertEqual(script.get_logs(), b'o0\ne0\no1\ne1\n')
        self.assertEqual(script.get_logs(stdout=False), b'e0\ne1\n')
        self.assertEqual(script.get_logs(stderr=False), b'o0\no1\n')

    def test_get_logs_tail(self):
        """
        We can choose how many lines to tail when getting logs from a
        container.

        NOTE: Lines are tailed *before* stdout/stderr are filtered out.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ])

        self.assertEqual(script.get_logs(tail='all'), b'o0\ne0\no1\ne1\n')
        self.assertEqual(script.get_logs(tail=10000), b'o0\ne0\no1\ne1\n')
        self.assertEqual(script.get_logs(tail=0), b'')
        self.assertEqual(script.get_logs(tail=1), b'e1\n')
        self.assertEqual(script.get_logs(tail=2), b'o1\ne1\n')
        # The entries are tailed *before* they're filtered. :-(
        self.assertEqual(script.get_logs(stderr=False, tail=1), b'')
        self.assertEqual(script.get_logs(stderr=False, tail=2), b'o1\n')
        self.assertEqual(script.get_logs(stderr=False, tail=3), b'o1\n')
        self.assertEqual(script.get_logs(stderr=False, tail=4), b'o0\no1\n')

    def test_get_logs_timestamps(self):
        """
        We can ask for timestamps on our logs.
        """
        before = datetime.utcnow()
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ])
        after = datetime.utcnow()

        self.assertEqual(script.get_logs(), b'o0\ne0\no1\ne1\n')
        raw_lines = script.get_logs(timestamps=True).splitlines()

        earlier = before
        for line, expected in zip(raw_lines, [b'o0', b'e0', b'o1', b'e1']):
            ts, ln = line.split(b' ', 1)
            self.assertEqual(ln, expected)
            # Truncate the nanoseconds, because we can't parse them.
            ts = (ts[:26] + ts[-1:]).decode('utf8')
            ts = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%fZ')
            self.assertLess(earlier, ts)
            earlier = ts
        self.assertLess(earlier, after)

    def test_stream_logs_timeout(self):
        """
        We can stream logs with a timeout.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ], delay=0.25, wait=False)

        time.sleep(0.01)
        lines = []
        with self.assertRaises(TimeoutError):
            for line in script.stream_logs(tail=0, timeout=0.3):
                lines.append(line)
        # We missed the first line and time out before the third.
        self.assertEqual(lines, [b'e0\n'])

        lines = []
        for line in script.stream_logs(tail=0, timeout=1.0):
            lines.append(line)
        # We should get the third and fourth now.
        self.assertEqual(lines, [b'o1\n', b'e1\n'])

    def test_stream_tail_all(self):
        """
        We can stream logs, including old logs, with a timeout.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ], delay=0.25, wait=False)

        time.sleep(0.01)
        lines = []
        with self.assertRaises(TimeoutError):
            for line in script.stream_logs(tail='all', timeout=0.3):
                lines.append(line)
        # We get the (old) first line and time out before the third.
        self.assertEqual(lines, [b'o0\n', b'e0\n'])

        lines = []
        for line in script.stream_logs(tail='all', timeout=1.0):
            lines.append(line)
        self.assertEqual(lines, [b'o0\n', b'e0\n', b'o1\n', b'e1\n'])

    def test_stream_logs_stdout(self):
        """
        We can choose stdout when streaming logs.
        """
        script = self.run_logs_container([
            'echo "first"',
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ], delay=0.2, wait=False)
        time.sleep(0.01)

        lines = []
        for line in script.stream_logs(stderr=False, tail=0, timeout=1.5):
            lines.append(line)
        self.assertEqual(lines, [b'o0\n', b'o1\n'])

    def test_stream_logs_stderr(self):
        """
        We can choose stderr when streaming logs.
        """
        script = self.run_logs_container([
            'echo "o0"', 'echo "e0" >&2',
            'echo "o1"', 'echo "e1" >&2',
        ], delay=0.2, wait=False)
        time.sleep(0.01)

        lines = []
        for line in script.stream_logs(stdout=False, timeout=1.5):
            lines.append(line)
        self.assertEqual(lines, [b'e0\n', b'e1\n'])

    def test_wait_for_logs_matching(self):
        """
        This behaves like calling the underlying wait_for_logs_matching()
        function with the container object as the first parameter.
        """
        script = self.run_logs_container([
            'echo "hi"',
            'echo "heya" >&2',
            'echo "hello"',
        ], delay=0.2, wait=False)

        script.wait_for_logs_matching(EqualsMatcher('hello'))
        with self.assertRaises(RuntimeError):
            script.wait_for_logs_matching(EqualsMatcher('goodbye'))

    def test_wait_for_logs_matching_timeout(self):
        """
        If we take too long to get a match, we time out.
        """
        script = self.run_logs_container([
            'echo "hi"',
            'echo "heya" >&2',
            'echo "hello"',
        ], delay=0.2, wait=False)
        with self.assertRaises(TimeoutError):
            script.wait_for_logs_matching(EqualsMatcher('hello'), timeout=0.1)

    def test_http_client(self):
        """
        We can get an HTTP client from the container object.
        """
        self.assertEqual(self.definition._http_clients, [])
        self.definition._create_kwargs = {
            'ports': {'8000/tcp': ('127.0.0.1', '10701')},
        }
        with self.definition as base:
            client = base.http_client()
            self.assertEqual(
                client._base_url.to_text(), 'http://127.0.0.1:10701')
            # Client is stashed for cleanup.
            self.assertEqual(self.definition._http_clients, [client])
        # Client is cleaned up at the end.
        self.assertEqual(self.definition._http_clients, [])


class TestNetworkDefinition(unittest.TestCase, DefinitionTestMixin):
    def setUp(self):
        self._setup()

    def make_definition(self, name, helper=None):
        return NetworkDefinition(name, helper=helper)


class TestVolumeDefinition(unittest.TestCase, DefinitionTestMixin):
    def setUp(self):
        self._setup()

    def make_definition(self, name, helper=None):
        return VolumeDefinition(name, helper=helper)
