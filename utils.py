from osgeo import gdal 
import numpy as np

def get_indxs_from_raster_coords(geo_ref, x, y):
    top_left_x, top_left_y, we_resolution, ns_resolution = geo_ref
    
    i = int( (y - top_left_y) /ns_resolution ) * -1 # in qgis2 it was without * -1
    j = int( (x - top_left_x) /we_resolution )

    return i, j

def get_coords_from_raster_indxs(geo_ref, i, j):
    top_left_x, top_left_y, we_resolution, ns_resolution = geo_ref

    y = ( top_left_y - (i+1.5)*we_resolution ) 
    x = top_left_x - (j-.5)*ns_resolution * -1 # in qgis2 it was without *-1

    return x  , y 

def get_whole_raster(layer):
    provider = layer.dataProvider()
    extent = provider.extent()
    
    rows = layer.height()
    cols = layer.width()
    dx = -1*(extent.xMinimum() - extent.xMaximum())/(cols)
    dy = -1*(extent.yMinimum() - extent.yMaximum())/(rows)
    top_left_x = extent.xMinimum()
    top_left_y = extent.yMaximum()
    geo_ref = (top_left_x, top_left_y, dx, dy)


    raster_path = layer.source()
    ds = gdal.Open(raster_path) 
    band1 = np.array(ds.GetRasterBand(1).ReadAsArray())
    band2 = np.array(ds.GetRasterBand(2).ReadAsArray())
    band3 = np.array(ds.GetRasterBand(3).ReadAsArray())

    return (band1,band2,band3), geo_ref
