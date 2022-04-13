# RasterTracer

RasterTracer is a plugin for semi-automatic digitizing of an underlying raster
layer in QGis.  
It is useful, for example, when you need to digitize a scanned
topographic map, with curved black lines representing lines of equal heights of
the surface (contours). 
Instead of creating this curved vector line by manually clicking
at each segment of this curved line, with this plugin you
can click at the beginning of the curved line and at the end of the curved
line, and it will automatically trace over black pixels (or pixels that are
almost black) starting from the beginning to the end. 
By using this plugin you reduce
clicks while digitizing raster maps. 

The process is show here: 

<img src="screen.gif" width="640" />

## Usage

Tracing is enabled only if the selected vector layer is in the editing mode.

The geometry type of the vector layer has to be MultiLineString / MultiCurve.

You can choose the color that will be traced over in the raster image. 
To do this, check the box `trace color` and select the desired color in
the dialog window.

If `trace color` is not checked, the plugin will try to trace the color that is 
similar to the color of the pixel on the map at the place where you clicked the
last time.
This means that each time you click on the map, it will trace a slightly
different color.
This slows down tracing a bit, but may be useful if the color of the line you are
tracing varies over the map.

## What image can it trace?

Right now the plugin can trace images that have a standard RGB color space. 
It has no support for any black and white, grey, or indexed images. 
This means that if your image has an unsupported colorspace, 
you have to convert the colorspace of your image to RGB first. This can be done in QGis with:

`Processing >> Toolbox >> GDAL >> Raster conversion >> PCT to RGB` 

or directly in the CLI with:

`pct2rgb.py <infile> <outfile> -of GTiff -b 1`

Also in the current version there are some issues when coordinate system 
of the raster layer differs from the coordinate system of the project.
It might be useful to convert the image that will be processed to the same coordinate
system used by the QGis project before importing. For example, the command bellow
converts a geotiff image (already georeferenced) to an `EPSG:4326` coordinate system.

`gdalwarp -t_srs EPSG:4326 -of GTiff infile.tif outfile.tif`

__NOTE__: `pct2rgb.py` and `gdalwarp` are part of the GDAL package.

## Useful keys


`b` - delete last segment

`a` - switch between "trace" mode and "straight-line" mode.

`Esc` - cancel tracing segment. Useful when raster_tracer struggles to find 
a good path between clicked points (Usually when points are far from each other).
