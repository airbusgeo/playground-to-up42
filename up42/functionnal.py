# Standard libraries
import enum
import json
import pathlib
import re
import requests
import shutil

# Third-party libraries
import docker
import loguru
import schema
import yaml

# Local libraries
import up42.exceptions as exceptions
import up42.schemas as schemas
import up42.streamers as streamers
import up42.utils as utils


# Docker clients
docker_client = docker.DockerClient(version='auto')
docker_api_client = docker.APIClient(version='auto')


# Enum
class OperatingSystem(enum.Enum):
    DEBIAN = 'debian'
    UBUNTU = 'ubuntu'
    CENTOS = 'centos'
    FEDORA = 'fedora'


def parse_config_file(config_file_path, validate=False):
    """Parse the config file and return a mapping.

    Arguments:
        config_file_path {click.Path}   -- A path to a valid YAML config file.
        validate {boolean}              -- Validate config file against schema

    """
    with open(config_file_path, 'r') as stream:
        try:
            loguru.logger.info('Parse configuration file with path: {}'.format(config_file_path))
            config = yaml.safe_load(stream)
        except yaml.YAMLError as error:
            raise exceptions.InvalidConfigFileException('Config file is invalid. '
                                                        'Following error occured: {}'.format(error))
        else:
            try:
                schemas.DOCKER_CONFIG_SCHEMA.validate(config['docker'])
            except schema.SchemaError as error:
                raise exceptions.InvalidConfigFileException('Config file is invalid. '
                                                            'Following error occured: {}'.format(error))

            else:
                loguru.logger.success('Configuration file is valid.')
                return config


def create_manifest(manifest_config, output_directory, filename='UP42Manifest.json'):
    """Create a valid manifest from the config file.

    Arguments:
        manifest_config {dict} -- A mapping describing the config to use for the manifest.
        output_directory {pathlib.Path} -- A path to the output directory for the manifest.
        filename {str} -- Name of the manifest JSON file.

    """
    # Fill manifest
    manifest = {
        '_up42_specification_version': 1,
        'name': manifest_config['name'],
        'type': manifest_config['type'],
        'tags': manifest_config['tags'],
        'display_name': manifest_config['display_name'],
        'description': manifest_config['description'],
        'parameters': manifest_config['parameters'],
        'machine': {
            'type': manifest_config['machine']
        },
        'input_capabilities': manifest_config['input_capabilities'],
        'output_capabilities': manifest_config['output_capabilities']
    }
    # Validate the manifest and save it if valid
    manifest = _validate_manifest(manifest)
    with open(output_directory / filename, 'w') as file:
        json.dump(manifest, file)
        loguru.logger.success('Manifest is properly saved.')


def _validate_manifest(manifest):
    """Validate manifest against schema and endpoint provided by UP42 platform.

    Arguments:
        manifest {dict} -- A mapping describing the config to use for the manifest.

    """
    # Validate the schema
    try:
        manifest = schemas.MANIFEST_SCHEMA.validate(manifest)
    except schema.SchemaError as error:
        raise exceptions.InvalidManifestException('Invalid manifest. Following errors encountered: {}'.format(error))
    # Validate the manifest against the endpoint
    headers = {'Content-Type': 'application/json'}
    try:
        r = requests.post('https://api.up42.com/validate-schema/block', headers=headers, data=json.dumps(manifest))
        r.raise_for_status()
    except requests.exceptions.HTTPError as error:
        raise exceptions.RequestException('Http Error: {}'.format(error))
    except requests.exceptions.ConnectionError as error:
        raise exceptions.RequestException('Error Connecting: {}'.format(error))
    except requests.exceptions.Timeout as error:
        raise exceptions.RequestException('Timeout Error: {}'.format(error))
    except requests.exceptions.RequestException as error:
        raise exceptions.RequestException('An unexpected error occured: {}'.format(error))

    # Check if response is ok
    response = json.loads(r.content)['data']
    if response['valid'] is False:
        raise exceptions.InvalidManifestException('Invalid manifest. Following errors encountered: '
                                                  '{}'.format(response['errors']))
    loguru.logger.success('Manifest is valid.')
    return manifest


def get_base_image_operating_system(base_image):
    """Dtermine the OS of the base image, running it in a container and parsing the /etc/os-release file.

    The /etc/os-release and /usr/lib/os-release files contain operating system identification data.
    The basic file format of os-release is a newline-separated list of environment-like shell-compatible variable
    assignments. It is possible to source the configuration from shell scripts, however, beyond mere variable
    assignments, no shell features are supported (this means variable expansion is explicitly not supported), allowing
    applications to read the file without implementing a shell compatible execution engine. Variable assignment values
    must be enclosed in double or single quotes if they include spaces, semicolons or other special characters outside
    of A–Z, a–z, 0–9. Shell special characters ("$", quotes, backslash, backtick) must be escaped with backslashes,
    following shell style. All strings should be in UTF-8 format, and non-printable characters should not be used.
    It is not supported to concatenate multiple individually quoted strings. Lines beginning with "#" shall be ignored
    as comments. Blank lines are permitted and ignored.

    * ID=
        A lower-case string (no spaces or other characters outside of 0–9, a–z, ".", "_" and "-") identifying the
        operating system, excluding any version information and suitable for processing by scripts or usage in generated
        filenames. If not set, defaults to "ID=linux". Example: "ID=fedora" or "ID=debian".

    Arguments:
        base_image {str} -- Base image to retrieve operating system of

    Returns:
        {OperatingSystem} -- The OS of the base image

    """
    loguru.logger.info('Try to extract the operating system name of the base image.')
    try:
        # Run base image in a container and fetch content of /etc/os-release file
        log_generator = docker_client.containers.run(base_image, entrypoint='cat /etc/os-release', remove=True,
                                                     stream=True, detach=False)

    except docker.errors.ImageNotFound:
        raise exceptions.DockerImageNotFound('Image does not exist on your computer.')
    except docker.errors.ContainerError as error:
        raise exceptions.DockerContainerError('Container exited with a non-zero exit code: {}'.format(error))
    except docker.errors.APIError as error:
        raise exceptions.DockerAPIError('The server returned an error: {}'.format(error))
    else:
        # Define the regex to match (look for the ``ID=operating_system`` field)
        regex = r'^ID=("{0,1})(debian|ubuntu|centos|fedora)("{0,1})$'

        # Parse logsand check if there is a match with the ID field in /etc/os-release file
        for line in log_generator:
            line = line.decode('utf-8')
            match = re.search(regex, line)
            if match is not None:
                break
        else:
            raise ValueError('Unable to fetch the operating system of the base image.')

        # Extract operating system
        value = match.group().replace('ID=', '').replace('"', '')
        operating_system = OperatingSystem(value)

        loguru.logger.success('Fetch of the operating system succeeded. Image is based on: {}'.format(operating_system))

        return operating_system


def copy_templates_files(output_directory, operating_system):
    """Copy template files to output directory.

    Arguments:
        output_directory {pathlib.Path}     -- A path to the output directory for the templates.
        operating_system {OperatingSystem}  -- Operating system of the base image

    """
    # Copy scripts
    templates_directory = pathlib.Path(__file__).parent / 'templates'
    shutil.copyfile(templates_directory / 'run.py', output_directory / 'run.py')
    shutil.copyfile(templates_directory / 'run_command.sh', output_directory / 'run_command.sh')

    # Copy Dockerfile based on base image operating system
    if operating_system == OperatingSystem.DEBIAN or operating_system == OperatingSystem.UBUNTU:
        shutil.copyfile(templates_directory / 'Dockerfiles' / 'debian.Dockerfile', output_directory / 'Dockerfile')
    elif operating_system == OperatingSystem.CENTOS:
        shutil.copyfile(templates_directory / 'Dockerfiles' / 'centos.Dockerfile', output_directory / 'Dockerfile')
    else:
        raise ValueError('This operating system is not supported yet: {}'.format(operating_system))

    loguru.logger.success('Templates files are successfully copied to: {}'.format(str(output_directory)))


def fetch_docker_image(docker_config):
    """Fetch docker image from repository if not yet exists

    Arguments:
        docker_config {dict} -- A mapping describing the config to use for the Docker image.

    Returns:
        {docker.Image} -- Docker image to be packaged

    """
    base_image = docker_config['input']['base_image']
    try:
        loguru.logger.info('Check if image has already been downloaded')
        docker_image = docker_client.images.get(base_image)
    except docker.errors.ImageNotFound:
        loguru.logger.info('Image does not seem to be downloaded. Try to pull it..')
        _pull_docker_image(base_image)
        docker_image = docker_client.images.get(base_image)
        return docker_image
    except docker.errors.APIError as error:
        raise exceptions.DockerImagePullException('Image pull failed with following error: {}'.format(error))
    else:
        loguru.logger.success('Image is already donwloaded. Fetch succeeded.')
        return docker_image


def _pull_docker_image(base_image):
    """Pull an image of the given name. Similar to the docker pull command.
    If no tag is specified, all tags from that repository will be pulled.

    Arguments:
        base_image {str} -- Image to pull (repository:tag)

    """
    try:
        # Pull image from repository with given tag
        log_streamer = docker_api_client.pull(base_image, stream=True, decode=True)

        # Stream image pull logs to logger
        image_pull_logs_thread = streamers.ImagePullLogsThread(log_streamer)
        image_pull_logs_thread.start()
        image_pull_logs_thread.join()

    except docker.errors.APIError as error:
        raise exceptions.DockerImagePullException('Image pull failed with following error: {}'.format(error))
    else:
        loguru.logger.success('Image pull succeeded')


def build_docker_image(docker_config, output_directory):
    """Build a Docker image compliant with the UP42 platform, which is a wrapper of an existing Playground algorithm.

    Arguments:
        docker_config {dict}            -- A mapping describing the config to use for the Docker image.
        output_directory {pathlib.Path} -- A path to the output directory for the templates.

    """
    # Retrieve manifest
    with open(output_directory / 'UP42Manifest.json', 'rb') as file:
        manifest = json.load(file)

    # Extract image command
    command = _extract_command(docker_config)
    loguru.logger.info('Command to be run: {}'.format(command))

    # Extract workdir
    workdir = _extract_workdir(docker_config)
    loguru.logger.info('Working directory to be used: {}'.format(workdir))

    # Build arguments to pass to Dockerfile
    build_args = {
        'BASE_IMAGE': docker_config['input']['base_image'],
        'MANIFEST': json.dumps(manifest),
        'PORT': str(docker_config['input']['exposed_port']),
        'PROCESS_ROUTE': str(docker_config['input']['routes']['process']),
        'HEALTHCHECK_ROUTE': str(docker_config['input']['routes']['healthcheck']),
        'RUN_COMMAND': str(command),
        'TYPE': str(docker_config['input']['type']),
        'WORKDIR': str(workdir)
    }

    # Build image
    try:
        streamer = docker_api_client.build(path=str(output_directory), tag=docker_config['output']['tag'], rm=True,
                                           buildargs=build_args, decode=True)

    except (docker.errors.BuildError, docker.errors.APIError, TypeError) as error:
        raise exceptions.DockerImageBuildException('Build failed with following error: {}'.format(error))

    build_logs_thread = streamers.ImageBuildLogsThread(streamer)
    build_logs_thread.start()
    build_logs_thread.join()

    # Check if image build succeeded
    if not build_logs_thread.succeeded:
        try:
            # Remove image if created
            docker_client.images.get(docker_config['output']['tag'])
            docker_client.images.remove(docker_config['output']['tag'])
        except docker.errors.ImageNotFound:
            pass
        raise exceptions.DockerImageBuildException('The build of the image failed. See logs above to have details.')
    loguru.logger.success('Build of the image succeeded.')


def _extract_command(docker_config):
    """Extract command from original docker image. Can be overriden in configuration file.

    Arguments:
        docker_config {dict} -- A mapping describing the config to use for the Docker image.

    Returns:
        {str} -- Command used to run the packaged application

    """
    # Retrieve user-defined command to be executed, if exists and well-defined
    if 'command' in docker_config['input'] and docker_config['input']['command'] is not None:
        return docker_config['input']['command']

    # Extract command to run the application (original image)
    docker_image = docker_client.images.get(docker_config['input']['base_image'])

    # Extract command from attributes
    try:
        command = docker_image.attrs['Config']['Cmd']
        if command is None:
            command = docker_image.attrs['Config']['Entrypoint']
    except KeyError:
        raise exceptions.DockerImageBuildException('Unable to fetch CMD and ENTRYPOINT instruction in image.')
    else:
        # Reformat command to string
        if isinstance(command, list):
            return ' '.join(command)
        return str(command)


def _extract_workdir(docker_config):
    """Extract working directory from original docker image. Can be overriden in configuration file.

    Arguments:
        docker_config {dict} -- A mapping describing the config to use for the Docker image.

    Returns:
        {str} -- Working directory used by the packaged application

    """
    # Retrieve user-defined command to be executed, if exists and well-defined
    if 'workdir' in docker_config['output'] and docker_config['output']['workdir'] is not None:
        return docker_config['output']['workdir']

    # Extract command to run the application (original image)
    docker_image = docker_client.images.get(docker_config['input']['base_image'])

    # Extract command from attributes
    try:
        workdir = docker_image.attrs['Config']['WorkingDir']
        if not workdir:
            workdir = '/'
    except KeyError:
        raise exceptions.DockerImageBuildException('Unable to fetch WorkingDir instruction in image.')
    else:
        return str(workdir)


def package(config_file, destination):
    """Package an existing Docker image following the UP42 specification. (cf. https://docs.up42.com/).

    Arguments:
        config_file {click.Path} -- A path to a valid YAML config file.
        destination {click.Path} -- A path to the output directory for the generated files.

    """
    try:
        # Variables
        output_directory = pathlib.Path(destination)

        # Parse config file
        config = parse_config_file(config_file, validate=True)

        # Fetch image if does not exist yet
        fetch_docker_image(config['docker'])

        # Fetch the operating system of the base image to determine which Dockerfile template to use
        operating_system = get_base_image_operating_system(config['docker']['input']['base_image'])

        # Create output directory if not exists
        utils.create_directory(output_directory, parents=True, exist_ok=True)

        # Create manifest
        create_manifest(config['manifest'], output_directory)

        # Copy template files to directory
        copy_templates_files(output_directory, operating_system)

        # Copy and fill Dockerfile
        build_docker_image(config['docker'], output_directory)

    except Exception as error:
        loguru.logger.error(error)
        raise error
    else:
        loguru.logger.success('Packaging of the application suceeded.')
