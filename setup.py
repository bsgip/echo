import setuptools
import sys

with open("README.md", "r") as fh:
    long_description = fh.read()

install_requires = [
    'pyomo>=3.5',
    'numpy>=1.21',
    'pandas>=1.4',
    'networkx>=2.7',
    'seaborn>=0.11',
    'typing-extensions>=4.1',
    'pydantic>=1.9',
    'tqdm>=4.63',
    'pyarrow>=7.0'
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
    version="1.0.4",
    description="For ",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=None,
    packages=setuptools.find_packages(),
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
