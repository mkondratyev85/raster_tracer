from osgeo import gdal 
from qgis.core import QgsCoordinateTransform
import numpy as np

class PossiblyIndexedImageError(Exception):
    pass

def get_indxs_from_raster_coords(geo_ref, xy):
    x, y = xy
    top_left_x, top_left_y, we_resolution, ns_resolution = geo_ref
    i = int( (y - top_left_y) /ns_resolution ) * -1 
    j = int( (x - top_left_x) /we_resolution )
    return i, j

def get_coords_from_raster_indxs(geo_ref, ij):
    i, j = ij
    top_left_x, top_left_y, we_resolution, ns_resolution = geo_ref
    y = ( top_left_y - (i+0.5)*ns_resolution ) 
    x = top_left_x - (j+0.5)*we_resolution * -1 
    return x  , y 

def get_whole_raster(layer, project_instance):
    provider = layer.dataProvider()
    extent = provider.extent()

    project_crs = project_instance.crs()
    transform_from_source = QgsCoordinateTransform(provider.crs(), project_crs, 
                                                             project_instance)
    transform_to_source = QgsCoordinateTransform(project_crs, provider.crs(), 
                                                             project_instance)

    dx = layer.rasterUnitsPerPixelX()
    dy = layer.rasterUnitsPerPixelY()
    top_left_x = extent.xMinimum()
    top_left_y = extent.yMaximum()

    #print(project_instance.crs().authid())
    #print(provider.crs().authid())
    #print(layer.crs().authid())
    #print("transformer: ", transform_from_source.transform(top_left_x, top_left_y))
    #print("original: ", top_left_x, top_left_y)

    geo_ref = (top_left_x, top_left_y, dx, dy)

    to_indexes = lambda x, y : get_indxs_from_raster_coords( 
                                geo_ref, transform_to_source.transform(x, y))
    to_coords = lambda i, j : transform_from_source.transform(
                               *get_coords_from_raster_indxs(geo_ref, (i,j)))
    to_coords_provider = lambda i, j :  \
                                 get_coords_from_raster_indxs(geo_ref, (i,j))
    to_coords_provider2 = lambda x, y :  \
                                 transform_to_source.transform(x, y)


    raster_path = layer.source()
    ds = gdal.Open(raster_path) 
    try:
        band1 = np.array(ds.GetRasterBand(1).ReadAsArray())
        band2 = np.array(ds.GetRasterBand(2).ReadAsArray())
        band3 = np.array(ds.GetRasterBand(3).ReadAsArray())
    except AttributeError:
        raise PossiblyIndexedImageError
    #geo_ref2  = ds.GetGeoTransform()
    #top_left_x_, we_resolution_, _, top_left_y_, _, ns_resolution_ = geo_ref2

    #print(extent.xMaximum(), extent.yMaximum(), extent.xMinimum(), extent.yMinimum())
    ##[print(dir(layer))
    #print("!!!!!!")
    #print(dx, dy)
    #print(top_left_x, top_left_y)
    #print("!!!!!!")
    #print(layer.crs().authid())
    #print(provider.crs().authid())
    #print("!!!!!!!")
    ##layer.setCrs(crs)
    #print(extent.xMaximum(), extent.yMaximum(), extent.xMinimum(), extent.yMinimum())
    #print(layer.extent())
    #print(layer.rasterUnitsPerPixelX(), layer.rasterUnitsPerPixelY())
    #print(layer.crs().authid())
    #print(ds.GetProjection())
    ##print(dir(provider))
    #print("!!!!!!!")
    #print("!!!!!!!!!!!!!!!")

    return (band1,band2,band3), to_indexes, to_coords, to_coords_provider, \
                                                       to_coords_provider2
