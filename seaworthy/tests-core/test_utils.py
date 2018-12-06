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
