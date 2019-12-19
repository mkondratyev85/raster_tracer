# RasterTracer

RasterTracer is a plugin for semi-automatic digitizing of underlying raster
layer in QGis.  
It is useful, for example, when you need to digitize a scanned
topographic map, with curved black lines representing lines of equal heights of
the surface. 
Instead of creating this curved vector line by manually clicking
at each segment of this curved line to create multi-line, with this plugin you
can click at the beginning of the curved line and at the end of the curved
line, and it will automatically trace over black pixels (or pixels that are
almost black) from the beginning to the end. 
By using this plugin you reduce
clicks while digitizing raster maps. 

This process is show here: 

<img src="screen.gif" width="640" />

## Usage

Tracing is enable only if selected vector layer is in the editing mode.

For better result you can choose the color that will be traced over. 
To do this, check the box `trace color` and select desirable color in dialog window.

If `trace color` is unset, the pluging will try to trace the color that is 
similar to the color of the pixel on the map at a place where you cliked last time.
It means, that each time you click on the map, it will trace slightly different color.
It slows down tracing a bit, but it may be useful if the color of the line you are tracing
varies.

## What image can it trace?

Right now the plugin can trace over images that have standard RGB color space. 
It has no support for any black and white, grey, or indexed images. 
It means that if you have to trace over images with such unsupported colorspace, 
first you have to convert colorspace of your image to RGB.


## Useful keys


`b` - delete last segment

`a` - switch between "trace" mode and "single-line" mode.
