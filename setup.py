from setuptools import find_packages, setup

requirements = [
    'attrs',
    'docker >= 2.4.0',
    'stopit >= 1.0.0',
]

test_requirements = [
    'pytest>=3.0.0',
    'testtools',
]

setup(
    name='seaworthy',
    version='0.1.0.dev0',
    license='BSD',
    url='https://github.com/praekeltfoundation/seaworthy',
    description='Test Docker container images',
    author='Praekelt.org SRE team',
    author_email='sre@praekelt.org',
    packages=find_packages(),
    install_requires=requirements,
    tests_require=test_requirements,
    extras_require={
        'test': test_requirements,
        'pep8test': [
            'flake8',
            'flake8-import-order',
            'pep8-naming',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Testing',
    ],
)
