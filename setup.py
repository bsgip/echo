import setuptools
import sys

with open("README.md", "r") as fh:
    long_description = fh.read()

install_requires = [
    'pyomo>=3.3',
    'numpy>=1.16.3',
    'pandas',
    'networkx'
]
tests_require = [
    "pytest",
    "pytest-timeout",
    "hypothesis[numpy]"
]

if sys.version_info < (3, 7):
    install_requires.append('dataclasses')

setuptools.setup(
    name="echo",
    version="0.0.1",
    description="For ",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=None,
    classifiers=[
    ],
    install_requires=install_requires,
    python_requires='>=3.6',
    extras_require={
        "validation": ["mypy"],
        "test": tests_require,
    },
    setup_requires=['pytest-runner'],
    tests_require=tests_require
)
