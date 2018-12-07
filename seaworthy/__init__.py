"""
seaworthy
~~~~~~~~~

.. todo::

   Write some API reference docs for :mod:`seaworthy`.
"""

from .helpers import DockerHelper
from .stream.logs import wait_for_logs_matching
from .utils import output_lines

__all__ = ['DockerHelper', 'output_lines', 'wait_for_logs_matching']

__version__ = '0.4.1'
