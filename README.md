# RasterTracer

RasterTracer is a plugin for semi-automatic digitizing of underlying raster layer in QGis. 

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


## Useful keys


`b` - delete last segment

`a` - switch between "trace" mode and "single-line" mode.
