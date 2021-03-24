# Third-party libraries
import requests


class UP42PackagingException(Exception):
    """Base exception for all UP42 packaging library specific errors."""


class RequestException(requests.exceptions.RequestException, UP42PackagingException):
    """There was an ambiguous exception that occurred while handling your request."""


class InvalidManifestException(UP42PackagingException):
    """There was an ambiguous exception that occured while validating the manifest schema."""


class InvalidConfigFileException(UP42PackagingException):
    """There was an ambiguous exception that occured while loading the config file."""


class DockerImageBuildException(UP42PackagingException):
    """There was an ambiguous exception that occured while building the Docker image."""


class DockerImagePullException(UP42PackagingException):
    """There was an ambiguous exception that occured while pulling a Docker image."""


class DockerImageNotFound(UP42PackagingException):
    """There was an ambiguous exception that occured while trying to get a docker image."""


class DockerContainerError(UP42PackagingException):
    """There was an ambiguous exception that occured while container exists with a non-zero exit code."""


class DockerAPIError(UP42PackagingException):
    """There was an ambiguous exception that occured while the server returned an error."""
