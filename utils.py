from osgeo import gdal
from qgis.core import QgsCoordinateTransform
import numpy as np


class PossiblyIndexedImageError(Exception):
    pass


def get_indxs_from_raster_coords(geo_ref, xy):
    x, y = xy
    top_left_x, top_left_y, we_resolution, ns_resolution = geo_ref
    i = int((y - top_left_y) / ns_resolution) * -1
    j = int((x - top_left_x) / we_resolution)
    return i, j


def get_coords_from_raster_indxs(geo_ref, ij):
    i, j = ij
    top_left_x, top_left_y, we_resolution, ns_resolution = geo_ref
    y = (top_left_y - (i + 0.5) * ns_resolution)
    x = top_left_x - (j + 0.5) * we_resolution * -1
    return x, y


def get_whole_raster(layer, project_instance):
    provider = layer.dataProvider()
    extent = provider.extent()

    project_crs = project_instance.crs()
    trfm_from_src = QgsCoordinateTransform(provider.crs(),
                                           project_crs,
                                           project_instance)
    trfm_to_src = QgsCoordinateTransform(project_crs,
                                         provider.crs(),
                                         project_instance)

    dx = layer.rasterUnitsPerPixelX()
    dy = layer.rasterUnitsPerPixelY()
    top_left_x = extent.xMinimum()
    top_left_y = extent.yMaximum()

    geo_ref = (top_left_x, top_left_y, dx, dy)

    to_indexes = lambda x, y: get_indxs_from_raster_coords(
                        geo_ref,
                        trfm_to_src.transform(x, y))
    to_coords = lambda i, j: trfm_from_src.transform(
                      *get_coords_from_raster_indxs(geo_ref, (i, j)))
    to_coords_provider = lambda i, j:\
        get_coords_from_raster_indxs(geo_ref,
                                     (i, j))
    to_coords_provider2 = lambda x, y: trfm_to_src.transform(x, y)
    raster_path = layer.source()
    ds = gdal.Open(raster_path)
    try:
        band1 = np.array(ds.GetRasterBand(1).ReadAsArray())
        band2 = np.array(ds.GetRasterBand(2).ReadAsArray())
        band3 = np.array(ds.GetRasterBand(3).ReadAsArray())
    except AttributeError:
        raise PossiblyIndexedImageError

    return ((band1, band2, band3), to_indexes, to_coords,
            to_coords_provider, to_coords_provider2)
