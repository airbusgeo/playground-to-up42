# Standard libraies
import argparse
import base64
import enum
import json
import pathlib
import sys
import time

# Third-party libraries
import geojson
import pyproj
import rasterio
import requests


# Constants
P3857 = pyproj.Proj(init='epsg:3857')
P4326 = pyproj.Proj(init='epsg:4326')

INPUT_FOLDER = '/tmp/input'
OUTPUT_FILE = '/tmp/output/data.json'


# Enums
class AlgorithmType(enum.Enum):
    """Available algorithm types."""
    OBJECT_DETECTION = 'objectDetectionAOI'
    CHANGE_DETECTION = 'changeDetectionAOI'

    def __str__(self):
        return self.value


# Utils
def get_tiles_couples(input_path=INPUT_FOLDER):
    """Read data.json file in input folder and extract all tiles, as couples, to be processed.

    Arguments:
        input_path {str} -- Folder where to find tiles and GeoJSON summary

    Returns:
        {list} -- A list of tuples of tiles to be processed

    """
    # Check if data.json exists
    geojson_filepath = pathlib.Path(input_path) / 'data.json'
    if not geojson_filepath.exists():
        raise FileNotFoundError('The geojson summary file at the root of the input folder does not exist.')

    # Parse it
    with open(geojson_filepath.as_posix(), 'r') as file:
        data = geojson.load(file)

        mapping = {}
        # Remap features
        for feature in data['features']:
            # Exract tile relative path
            #tile_path = feature['properties']['up42.data.aoiclipped'] # v1
            tile_path = feature['properties']['up42.data_path'] # v2
            
            # Extract tile indexes (template = folder / tile_id + '_' + indexes + '.tif')
            indexes = tile_path.split('/')[1].replace('.tif', '').split('_')[-1]

            # Fill mapping dictionnary
            if indexes not in mapping:
                mapping[indexes] = []
            absolute_tile_path = (pathlib.Path(input_path) / tile_path).as_posix()
            mapping[indexes].append(absolute_tile_path)

        tiles_couples = []
        # To list of tiles couple
        for couple in mapping.values():
            couple.sort()
            tiles_couples.append(tuple(couple))

        return tiles_couples


def get_common_properties(input_path=INPUT_FOLDER):
    """Read data.json file in input folder and extract common properties (everything except up42.data.aoiclipped or up42.data_path).

    Arguments:
        input_path {str} -- Folder where to find tiles and GeoJSON summary

    Returns:
        {dict} -- A mapping of properties

    """
    # Check if data.json exists
    geojson_filepath = pathlib.Path(input_path) / 'data.json'
    if not geojson_filepath.exists():
        raise FileNotFoundError('The geojson summary file at the root of the input folder does not exist.')

    # Parse it
    with open(geojson_filepath.as_posix(), 'r') as file:
        data = geojson.load(file)

        # Take properties of first feature, if exists
        properties = {}
        if len(data['features']) >= 1:
            properties = data['features'][0]['properties']
            #properties.pop('up42.data.aoiclipped', None) # v1
            properties.pop('up42.data_path', None) # v2

        return properties


def check_dataset_integrity(tiles_couples, type):
    """Check that all couples of tiles have same length and match the algorithme type of detection.

    Arguments:
        tiles_couples {list} -- List of tiles couples to process
        type {str}              -- Type of algorithm to run (either ``objectDetectionAOI`` or ``changeDetectionAOI``)

    Raises:
        {AssertionError}    --When couples have different length or length does not match required length
        {ValueError}        -- When algorithm type is unknown

    """
    # Check all couples have same lengths
    couple_length_set = set(map(len, tiles_couples))
    if len(couple_length_set) not in (0, 1):
        raise ValueError('All couples must have the same number of images!')

    if args.type == AlgorithmType.OBJECT_DETECTION:
        assert couple_length_set == set([1]), 'Object detection must work with a single image at a time.'
    elif args.type == AlgorithmType.CHANGE_DETECTION:
        assert couple_length_set == set([2]), 'Change detection must work with two images at a time.'
    else:
        raise ValueError('Invalid detection type.')


def get_tile_transform(tile_path):
    """Read a GeoTIFF image and get its Affine transformation.

    Arguments:
        tile_path {str} -- Path of the tile to get transform from

    Returns:
        {affine.Affine} -- Affine transformation of the given tile (pixels to WebMercator CRS)

    """
    with rasterio.open(tile_path, 'r') as dataset:
        return dataset.transform


def encode_tile(tile_path):
    """Encode image file to base64.

    Arguments:
        tile_path {str} -- Path of the tile to encode

    Returns:
        {bytes} -- Encoded tile using Base64

    """
    with open(tile_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def apply_projection(xy, transform):
    """Convert (x, y) coordinates (tile reference) to (lon, lat) system.

    Arguments:
        xy {list}                   -- Position of a polygon vertex, as [X, Y] coordinates
        transform {affine.Affine}   -- Affine transformation of the given tile (pixels to WebMercator CRS)

    Returns:
        {list} -- Position in Geographic Coordinate Reference System (4326)
    """
    # Tile reference to world reference (3857 a.k.a Web Mercator)
    X, Y = transform * xy
    # Web Mercator (X, Y) to (longitude, latitude)
    return pyproj.transform(P3857, P4326, X, Y)


def apply_transformation(features, transform):
    """Convert pixels coordinates to (lon, lat) values in features.

    Arguments:
        features {list}             -- List of predictions as valid GeoJSON features (in tile coordinates)
        transform {affine.Affine}   -- Affine transformation of the given tile (pixels to WebMercator CRS)

    Returns:
        {list} -- List of reprojected predictions (in geographic CRS), as valid GeoJSON features

    """
    new_features = []
    for feature in features:
        # Transform geometry
        new_geometry = transform_geometry(feature['geometry'], transform)
        new_feature = geojson.Feature(geometry=new_geometry, properties=feature['properties'])
        new_features.append(new_feature)
    return new_features


def save_output_to_disk(result, output_file=OUTPUT_FILE):
    """Write the result data to the /tmp/output directory.

    Arguments:
        result {geojson.FeatureCollection} -- Collection of predictions
        output_file {str} -- Path where to store GeoJSON file

    """
    with open(output_file, "w") as fp:
        fp.write(json.dumps(result))


def transform_geometry(geometry, transform):
    """Transform geometry coordinates to (longitude, latitude) values.

    Args:
        geometry {geojson.Geometry} -- Geometry of the geometry to transform
        transform {affine.Affine}   -- Affine transformation of the given tile (pixels to WebMercator CRS)

    Returns:
        {geojson.Geometry} -- Reprojected geometry

    """
    if geometry['type'] == 'Point':
        new_coordinates = apply_projection(geometry['coordinates'], transform)
        return geojson.Point(new_coordinates)
    elif geometry['type'] == 'Polygon':
        new_coordinates = [[apply_projection(position, transform) for position in geometry['coordinates'][0]]]
        return geojson.Polygon(new_coordinates)
    else:
        raise ValueError('Unknown geometry: {}'.format(geometry))


# Predictor
class Predictor(object):
    """Predictor class used to run predictions on a whole dataset and reproject them in Geographic CRS.

    Arguments:
        port {int}              -- Port to be used to run processing
        process_route {str}     -- Route to be used to run processing
        healthcheck_route {str} -- Route to be used to check healthiness of the application
        algorithm_type {str}    -- Type of the algorithm used (either ``objectDetectionAOI`` or ``changeDetectionAOI``)
        resolution {float}      -- Resolution in meters/pixel of the tile to process

    """

    def __init__(self, port, process_route, healthcheck_route, algorithm_type, resolution):
        # Set attributes
        self._port = port
        self._process_route = process_route
        self._healthcheck_route = healthcheck_route
        self._type = algorithm_type
        self._resolution = resolution

        # Try health check every 5 seconds until it workds. After 5 tries, abort
        for _ in range(10):
            try:
                self._healthcheck()
            except (AssertionError, requests.exceptions.RequestException):
                print('Ping healthcheck')
                time.sleep(10)
                continue
            else:
                print('Healtcheck responded a 200 HTTP code. Start processing tiles...')
                break
        else:
            raise requests.exceptions.RequestException('After 5 retries, Health check did not respond a 200 code.')

    def run_predictions_on_dataset(self, input_path):
        """Run predictions on a list of tile couples and return predictions as a Feature collection.

        Arguments:
            input_path {str} -- Folder where to find tiles and GeoJSON summary

        Returns:
            {geojson.Featurecollection} -- Collection of predictions in Geographic CRS

        """
        # Retrieve tiles to be processed in input folder
        tiles_couples = get_tiles_couples(input_path=input_path)

        # Check dataset integrity (Couples lengths, right number of tiles per couples, etc.)
        check_dataset_integrity(tiles_couples, args.type)

        # Run predictions on tiles couples asynchronously
        features_lists = [self._run_predictions_on_tile(couple) for couple in tiles_couples]

        # Extract properties from data block
        data_block_properties = get_common_properties(input_path=input_path)

        # Aggregate geojson
        features = [feature for features_list in features_lists for feature in features_list]
        collection = geojson.FeatureCollection(features, data_block_properties=data_block_properties)

        return collection

    def _run_predictions_on_tile(self, tiles_couple):
        """Run predictions on a couple of tiles (1 = object detection, 2 = change detection) and return output.

        Arguments:
            tiles_couple {tuple} -- Couple of tiles to be processed by the algorithm, as a tuple

        Returns:
            {list} -- List of predictions as valid GeoJSON features

        """
        def run_process(encoded_tiles, port, process_route, resolution):
            """Run process for the given couple of tile.

            Arguments:
                encoded_tiles {list}    -- List of encoded tiles, using Base64, to process
                port {int}              -- Port to be used to run processing
                process_route {str}     -- Route to be used to run processing
                resolution {float}      -- Resolution in meters/pixel of the tile to process

            Returns:
                {list} -- List of predictions as valid GeoJSON features

            """
            # Build payload
            data = dict(resolution=resolution, tiles=encoded_tiles)
            # Launch request
            if 'http' in process_route:
                url = process_route
            else:
                "http://0.0.0.0:{port}{process_route}".format(port=port, process_route=process_route)
            url = process_route
            r = requests.post(url, json=data)
            r.raise_for_status()
            # Get content as JSON object
            return json.loads(r.content.decode('utf-8'))['features']

        print('Run process on tile(s): {}'.format(tiles_couple))
        # Read image and transformation
        transform = get_tile_transform(tiles_couple[0])
        # Encode image to base64
        encoded_tiles = [encode_tile(tile) for tile in tiles_couple]
        # Run predict process
        features = run_process(encoded_tiles, self._port, self._process_route, self._resolution)
        print('Result: {}\n'.format(features))
        # Transform coordinates to (longitude, latitude)
        return apply_transformation(features, transform)

    def _healthcheck(self):
        """Check if the detection application is running well (must return a 200).

        Raises:
            {AssertionError} -- When healthcheck does not respond a 200 HTTP code

        """
        # Launch request
        if 'http' in self._healthcheck_route:
            r = requests.get(self._healthcheck_route)
        else:
            r = requests.get('http://0.0.0.0:{port}{route}'.format(port=self._port, route=self._healthcheck_route))

        r = requests.get(self._healthcheck_route)
        r.raise_for_status()
        # Check status code
        assert r.status_code == 200, 'Application is not responding a 200 (OK) for healthcheck'


if __name__ == "__main__":

    # Define and parse arguments
    parser = argparse.ArgumentParser("Run predictions on GeoTIFF tiles.")

    parser.add_argument('--port', type=str, help='Port exposed by the Flask application.')
    parser.add_argument('--process_route', type=str, help='Route to be used to send tiles and run predictions')
    parser.add_argument('--healthcheck_route', type=str, help='Route to be used to check application health')
    parser.add_argument('--type',  type=AlgorithmType, choices=list(AlgorithmType),
                        help='Type of algorithm to be packaged')
    parser.add_argument('--resolution', type=float, help='Resolution (meters/pixel) of the tiles to process')

    args = parser.parse_args()

    try:
        # Init predictor
        predictor = Predictor(args.port, args.process_route, args.healthcheck_route, args.type, args.resolution)

        # Run predictions on dataset
        results = predictor.run_predictions_on_dataset(INPUT_FOLDER)

        # Save output
        save_output_to_disk(results, output_file=OUTPUT_FILE)

    except Exception as error:
        print(error)
        sys.exit(1)
