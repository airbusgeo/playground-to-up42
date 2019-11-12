# Third-party libraries
import click
import loguru

# Local librairies
import up42.functionnal as functionnal


# Groups
@click.group()
def up42():
    """Main UP42-packaging project CLI"""
    pass


# Commands
@click.command()
@click.argument('config_file', type=click.Path(exists=True, file_okay=True))
@click.argument('destination', type=click.Path(dir_okay=True))
def package(config_file, destination):
    """Package an existing Docker image following the UP42 specification. (cf. https://docs.up42.com/).

    \b
    Arguments:
        config_file:  A path to a valid YAML config file.
        destination:  A path to the output directory for the generated files.
    """
    loguru.logger.info('Package the application...')
    functionnal.package(config_file, destination)


# Register commands
up42.add_command(package)


if __name__ == '__main__':
    up42()
