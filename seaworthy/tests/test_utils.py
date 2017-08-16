from testtools.assertions import assert_that
from testtools.matchers import Equals

from seaworthy.utils import resource_name


def test_resource_name():
    # Dummy test so that pytest passes
    assert_that(resource_name('foo'), Equals('test_foo'))
