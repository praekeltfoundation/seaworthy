from unittest import TestCase

from seaworthy.utils import resource_name


class DummyTest(TestCase):
    def test_resource_name(self):
        # Dummy test so that pytest passes
        self.assertEqual(resource_name('foo'), 'test_foo')
