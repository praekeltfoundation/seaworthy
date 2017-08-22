"""
This package contains "core" tests that don't depend on anything that isn't
already a non-optional dependency of Seaworthy itself.

We have strong opinions about the testing tools we use, and we understand that
other people may have equally strong opinions that differ from ours. For this
reason, we have decided that none of Seaworthy's core functionality will depend
on pytest, testtools, or anything else that might get in the way of how people
might wants to write their tests.

To make sure none of these dependencies accidentally creep in, all tests in
this package are run in an environment without any extra (or optional)
dependencies installed.
"""
