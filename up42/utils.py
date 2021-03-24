def create_directory(directory, parents=False, exist_ok=False):
    """Create the output directory if it is not already existing.

    Arguments:
        directory {pathlib.Path} -- A path to the output directory for the generated files.
        parents {bool} -- If parents is true, any missing parents of this path are created as needed;
                          If parents is false (the default), a missing parent raises FileNotFoundError.
        exist_ok {bool} -- If exist_ok is false, FileExistsError is raised if the target directory already exists.
                           If exist_ok is true, FileExistsError exceptions will be ignored.

    """
    directory.mkdir(parents=parents, exist_ok=exist_ok)
