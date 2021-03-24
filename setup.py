import io
import re
from setuptools import setup, find_packages

# Only packages the trainer and detection packages
REQUIRED_PACKAGES = [
    'click',
    'loguru',
    'docker>=3.6.0',
    'PyYAML',
    'schema'
]


with io.open('up42/__init__.py', 'rt', encoding='utf8') as f:
    version = re.search(
        r'__version__ = \'(.*?)\'', f.read(), re.M).group(1)

setup(
    name='up42',
    version=version,
    packages=find_packages(),
    entry_points='''
        [console_scripts]
        up42=up42.cli:up42
    ''',
    description='UP42 packaging toolset',
    long_description='A packaging util to deploy Docker image UP42 compliant.',
    include_package_data=True,
    author='Alexandre MAYEROWITZ',
    author_email='alexandre.mayerowitz@geoapi-airbusds.com',
    license='',
    install_requires=REQUIRED_PACKAGES,
    zip_safe=False)
