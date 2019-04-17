import unittest

from docker.models.containers import ExecResult

from seaworthy.utils import output_lines


class TestOutputLinesFunc(unittest.TestCase):
    def test_bytes(self):
        """String lines are parsed from output bytes."""
        self.assertEqual(output_lines(b'foo\nbar\n'), ['foo', 'bar'])

    def test_exec_result(self):
        """String lines are parsed from an ExecResult."""
        self.assertEqual(output_lines(ExecResult(128, b'foo\r\nbar\r\n')),
                         ['foo', 'bar'])

    def test_custom_encoding(self):
        """String lines can be parsed using a custom encoding."""
        self.assertEqual(output_lines(b'\xe1', encoding='latin1'), ['á'])

    def test_exec_result_error_exc(self):
        """ExecResult with nonzero exit code can raise exception."""
        with self.assertRaisesRegex(TimeoutError, 'x\r\ny'):
            output_lines(ExecResult(128, b'x\r\ny'), error_exc=TimeoutError)
        # No exception if the exit code is zero.
        self.assertEqual(output_lines(ExecResult(0, b':-)')), [':-)'])
