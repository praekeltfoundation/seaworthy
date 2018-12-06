import os
import re

from setuptools import find_packages, setup

HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    with open(os.path.join(HERE, *parts)) as f:
        return f.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string')


setup(
    name='seaworthy',
    version=find_version('seaworthy', '__init__.py'),
    license='BSD',
    url='https://github.com/praekeltfoundation/seaworthy',
    description='Test Docker container images',
    author='Praekelt.org SRE team',
    author_email='sre@praekelt.org',
    long_description=read('README.rst'),
    packages=find_packages(),
    install_requires=[
        'attrs>=17.4.0',
        'docker>=3.6,<4',
        'hyperlink',
        'requests',
    ],
    extras_require={
        'pytest': [
            'pytest>=3.0.0',
        ],
        'testtools': [
            'testtools',
        ],
        'test': [
            'pytest>=3.0.0',
            'responses',
            'testtools',
        ],
        'test-core': [
            'responses',
        ],
        'docstest': [
            'doc8',
            'readme_renderer',
            'Sphinx>=1.7,<1.8',
            'sphinx_rtd_theme',
        ],
        'pep8test': [
            'flake8',
            'flake8-import-order',
            'pep8-naming',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Pytest',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Testing',
    ],
    entry_points={
        'pytest11': ['seaworthy = seaworthy.pytest'],
    },
)
