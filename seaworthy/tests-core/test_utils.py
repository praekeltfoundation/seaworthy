"""
Tests for seaworthy.utils module.

Please note that these are "core" tests and thus may not depend on anything
that isn't already a non-optional dependency of Seaworthy itself.
"""

import unittest

from seaworthy.utils import resource_name


class DummyTest(unittest.TestCase):
    def test_resource_name(self):
        # Dummy test so that pytest passes
        self.assertEqual(resource_name('foo'), 'test_foo')
