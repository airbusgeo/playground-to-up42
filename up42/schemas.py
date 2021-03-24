# Third-party libraries
from schema import Schema, And, Use, Or


INPUT_SCHEMA = Schema({
    'base_image': And(Use(str), len),
    'exposed_port': Use(int),
    'type': Or('objectDetectionAOI', 'changeDetectionAOI'),
    'routes': {
        'healthcheck': And(Use(str), len),
        'process': And(Use(str), len)
    },
    'command': And(Use(str), len),
    'resolution': And(Use(float), lambda resolution: resolution > 0.0)
}, ignore_extra_keys=True)

OUTPUT_SCHEMA = Schema({
    'tag': And(Use(str), len),
    'workdir': And(Use(str), len)
}, ignore_extra_keys=True)

DOCKER_CONFIG_SCHEMA = Schema({
    'input': INPUT_SCHEMA,
    'output': OUTPUT_SCHEMA
}, ignore_extra_keys=True)


MANIFEST_SCHEMA = Schema({
    '_up42_specification_version': And(Use(int), lambda version: version == 2),
    'name': And(Use(str), len),
    'display_name': And(Use(str), len),
    'type': Or('data', 'processing'),
    'tags': Use(list),
    'description': Use(str),
    'parameters': Use(dict),
    'machine': {
        'type': Or('small', 'medium', 'large', 'xlarge', 'gpu_nvidia_tesla_k80')
    },
    'input_capabilities': Use(dict),
    'output_capabilities': Use(dict)
}, ignore_extra_keys=True)
