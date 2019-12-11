# Playground to UP42 packaging converter

A CLI to convert processing Docker images (deployed on ``Playground`` Platform) following the UP42 specification.

## Quickstart

### Rational

Whenever trying to publish a model to the **Playground**, a production capable code for each model must be accordingly
"wrapped" in an HTTP API with a healthcheck and a prediction endpoint.

### Installation

Installation is a straightforward python package application installation, e.g:

```bash
git clone https://github.com/airbusgeo/playground-to-up42.git
cd playground-to-up42
pip install .
```

This will install the **UP42** CLI with `up42` entrypoint.

### Usage

#### Root CLI

```bash
up42 --help

Usage: up42 [OPTIONS] COMMAND [ARGS]...

  Main UP42-packaging project CLI

Options:
  --help  Show this message and exit.

Commands:
  package  Package an existing Docker image following the UP42...

```

The root CLI exposes the `package` command.

#### UP42 packaging utils CLI

```bash
up42 package --help

Usage: up42 package [OPTIONS] CONFIG_FILE DESTINATION

  Package an existing Docker image following the UP42 specification. (cf.
  https://docs.up42.com/).

  Arguments:
      config_file:  A path to a valid YAML config file.
      destination:  A path to the output directory for the generated files.

Options:
  --help  Show this message and exit.

```

In order to package an algorithm, following the UP42 specification, you need to provide two arguments for the **package** command:

- a YAML configuration file *(see below for details)*
- an output directory path *(directory and its parents will be created if it does not exist)*

The configuration file should follow the template defined in the file ``up42/templates/config.yaml``, specifically:

```yaml
docker:
    input:
        base_image: 'repository:tag'        # Base image to use (the packaged algorithm)
        exposed_port: 8080                  # Port used by the Flask application
        type: 'objectDetectionAOI'          # Type of detection (either ``objectDetectionAOI`` or ``changeDetectionAOI``)
        routes:
            process: '/api/process'         # Route that takes a resolution and a list of base64-encoded tiles and runs predictions. It returns a valid GeoJSON, following the GeoPaaS API.
            healthcheck: '/api/healthcheck' # Route used to be sure the application is ruuning well
        command: null                       # Override, if not null, base image command instruction with user-defined command

    output:
        tag: 'test'                         # Tag of the built image
        workdir: null                       # Override, if not null. The WORKDIR instruction sets the working directory for any RUN, CMD, ENTRYPOINT, COPY and ADD instructions that follow it in the Dockerfile.

manifest:
    name: 'name'                            # Name of your block. This name must be unique for your account.
    display_name: 'Pretty name'             # Name of the block as displayed in the UP42 UI (no need to be unique)
    type: 'processing'                      # Either "data" or "processing". This provides a hint to the platform when validating workflows. 
    tags:                                   # List of tags used for searching and filtering blocks in the UP42 UI.
        - 'generic'
    description: 'Description'              # Free-text explanation of what your block does
    parameters: {}                          # For data blocks, list of all query parameters the block supports. For processing blocks, the run-time parameters that your block can optionally specify.
    machine: 'small'                        # Either "small", "medium", "large" or "xlarge"
    input_capabilities: {}                  # The capabilities that your block requires to run
    output_capabilities: {}                 # The capabilities that your block outputs when it is finished. 

```

Some explanations about the content of the configuration file:

- ``base_image``: the packager will look in your docker local environment if the given image exists. If no image matches, it will try to download the image from the given registry
- ``exposed_port``: Every image that needs to be packaged for UP42 must expose a port to be compliant with Playground spec. This port will be used by the wrapper to process the different tiles
- ``type``: This parameter defines the type of algorithm you want to package. For now, only ``objectDetectionAOI`` and ``changeDetectionAOI`` are allowed. The wrapper will then check if the input folder matches the expected type of algorithm (1 tile processed at a time for ``objectDetectionAOI``, 2 for ``changeDetectionAOI``)
- ``routes``: Two endpoints needs to be set:
  - ``Healthcheck``: This endpoint should return an http 200 OK on GET requests once the service is ready to accept incoming processing requests. If this endpoint cannot be reached or does not return a 200 OK , the service will be considered as unhealthy and will not receive requests to process. Typically, if the service needs time to initialize at startup, the healthcheck endpoint should return a non-200 code until the initialization is over and requests can actually be served. This endpoint will be called **5 times**, every **5 seconds**, until an http 200 OK is returned. Otherwise, we stop the process.
  - ``Processing``: This endpoint should accept POST requests and will receive requests containing an base64 encoded image payload embedded in a JSON document. The image you will receive will respect the specifications asked by your process, namely size and resolution. The payloads received by this endpoint are fixed and cannot be extended, if you require additional information this should be set in the URL.

- ``command``: In order for the wrapper to send the base-64 encoded tiles to the predictor, the REST application needs to be run in background. To do see, each docker image that needs to be packaged must expose a ``CMD`` instruction in its Dockerfile which is used to start the REST application, and do some other stuffs if necessary. For the packager to be generic, it will try to extract the ``CMD`` instruction of the base image and use it as default. In some cases, the user may want to override this parameter. To do so, a non-``null`` value must then be set in the configuration file to define a custom command to be set. Make sure this command can be executed with the working directory used by the final image.

- ``tag``: Once the build of the wrapping application is done, the packager will automatically tag your image with provided name. ``repository:tag`` format should be used.
- ``workdir``: Some application must start in a certain working directory to work. By default, the packager will extract the working directory defined in the base image and use it as default. This parameter can be overriden if ``workdir`` is set to non-``null`` value.

In few words, to package an algorithm, you need to follow the follwing steps:

1. Copy the configuration file anywhere you want.
2. Update the configuration file to suit your needs
3. Run:

```bash
up42 package [PATH_CONFIG_FILE] [PATH_TO_OUTPUT_DIRECTORY]
```

In the **output directory**, you will find several files:

- ``Dockerfile``: the **Dockerfile** template used to build the image
- ``run_command.sh``: a shell script that will be ran when you will run the produced image in a container. it basically runs the Flask application in background and execute the ``run.py`` in foreground.
- ``run.py``: a python script that reads GeoTIFF tiles in a ``/tmp/input`` folder, encode them in base 64 and send them to the process, parse the results, and a create a valid GeoJSON, projecting each detected polygons to longitude/latitude coordinates system.
- ``UP42Manifest.json``: the manifest that needs to respect the specification of UP42

#### Run application

To run the application, you need two folders, one with some GeoTIFF tiles (``input folder``) and a second one that will be used to place the output of the process (``output folder``).
To do so, you just need to run the following command, replacing what needs to be replaced (paths and tag):

```docker
docker run --rm -v [PATH_TO_INPUT_FOLDER]:/tmp/input -v [PATH_TO_OUTPUT_FOLDER]:/tmp/output [TAG_OF_YOUR_IMAGE]
```
