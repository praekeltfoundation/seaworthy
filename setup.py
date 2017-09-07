import os

from setuptools import find_packages, setup

HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    with open(os.path.join(HERE, *parts)) as f:
        return f.read()


setup(
    name='seaworthy',
    version='0.1.0.dev0',
    license='BSD',
    url='https://github.com/praekeltfoundation/seaworthy',
    description='Test Docker container images',
    author='Praekelt.org SRE team',
    author_email='sre@praekelt.org',
    long_description=read('README.rst'),
    packages=find_packages(),
    install_requires=[
        'attrs',
        'docker >= 2.4.0',
    ],
    extras_require={
        'pytest': [
            'pytest>=3.0.0',
        ],
        'testtools': [
            'testtools',
        ],
        'test': [
            'testtools',
            'pytest>=3.0.0',
        ],
        'docstest': [
            'doc8',
        ],
        'pep8test': [
            'flake8',
            'flake8-import-order',
            'pep8-naming',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: BSD License',
        'Framework :: Pytest',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Testing',
    ],
    entry_points={
        'pytest11': ['seaworthy = seaworthy.pytest'],
    },
)
