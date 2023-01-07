import sys
from setuptools import setup
from os import path

setup_file_dir = path.abspath(path.dirname(__file__))

try:
    with open(path.join(setup_file_dir, "README.md"), encoding="utf-8") as f:
        long_description = f.read()
except FileNotFoundError:
    print("README.md not found")
    sys.exit(1)

try:
    with open(path.join(setup_file_dir, "requirements.txt"), encoding="utf-8") as f:
        requirements = f.read()
except FileNotFoundError:
    print("requirements.txt not found")
    sys.exit(1)

setup(
    name="fritz-advanced-thermostat",
    version="0.1.1",
    description="A library for setting FRITZ!DECT thermostat values (e.g. offset, holidays, timer), that can't be set via AHA requests.",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url="https://github.com/mietzen/python-fritz-advanced-thermostat",
    author="Nils Stein",
    author_email="github.nstein@mailbox.org",
    license="MIT",
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        "Operating System :: OS Independent",
    ],
    keywords="fritzbox smarthome avm thermostat",
    packages=["fritz_advanced_thermostat"],
    install_requires=requirements.split('\n')
)

