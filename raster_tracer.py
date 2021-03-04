# -*- coding: utf-8 -*-
"""
/***************************************************************************
 RasterTracer
                                 A QGIS plugin
 This plugin traces the underlying raster map
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2019-11-09
        git sha              : $Format:%H$
        copyright            : (C) 2019 by Mikhail Kondratyev
        email                : mkondratyev85@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
# Initialize Qt resources from file resources.py
from .resources import *


# Import the code for the DockWidget
from .raster_tracer_dockwidget import RasterTracerDockWidget
import os.path


from qgis.core import QgsProject, QgsVectorLayer

from .pointtool import PointTool


class RasterTracer:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'RasterTracer_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Raster Tracer')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'RasterTracer')
        self.toolbar.setObjectName(u'RasterTracer')

        # print "** INITIALIZING RasterTracer"

        self.pluginIsActive = False
        self.dockwidget = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('RasterTracer', message)

    def add_action(self,
                   icon_path,
                   text,
                   callback,
                   enabled_flag=True,
                   add_to_menu=True,
                   add_to_toolbar=True,
                   status_tip=None,
                   whats_this=None,
                   parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/raster_tracer/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Trace Raster'),
            callback=self.run,
            parent=self.iface.mainWindow())

    # -------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        self.dockwidget = None

        self.pluginIsActive = False

        self.tool_identify.deactivate()

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        # print( "** UNLOAD RasterTracer")

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Raster Tracer'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    # -------------------------------------------------------------------------

    def activate_map_tool(self):
        ''' Activates map tool'''
        self.map_canvas.setMapTool(self.tool_identify)

    def run(self):
        """Run method that loads and starts the plugin"""

        if self.pluginIsActive:
            self.activate_map_tool()
            return

        self.pluginIsActive = True

        # print "** STARTING RasterTracer"

        # dockwidget may not exist if:
        #    first run of plugin
        #    removed on close (see self.onClosePlugin method)
        if self.dockwidget is None:
            # Create the dockwidget (after translation) and keep reference
            self.dockwidget = RasterTracerDockWidget()

        # connect to provide cleanup on closing of dockwidget
        self.dockwidget.closingPlugin.connect(self.onClosePlugin)

        # show the dockwidget
        self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget)
        self.dockwidget.show()

        self.map_canvas = self.iface.mapCanvas()
        # vlayer = self.iface.layerTreeView().selectedLayers()[0]
        self.tool_identify = PointTool(self.map_canvas, self.iface, self.turn_off_snap)
        # self.map_canvas.setMapTool(self.tool_identify)
        self.activate_map_tool()

        excluded_layers = [l for l in QgsProject().instance().mapLayers().values() 
                                                    if isinstance(l, QgsVectorLayer)]
        self.dockwidget.mMapLayerComboBox.setExceptedLayerList(excluded_layers)
        self.dockwidget.mMapLayerComboBox.currentIndexChanged.connect(self.raster_layer_changed)
        self.tool_identify.raster_layer_has_changed(self.dockwidget.mMapLayerComboBox.currentLayer())

        self.dockwidget.checkBoxColor.stateChanged.connect(self.checkBoxColor_changed)
        self.dockwidget.mColorButton.colorChanged.connect(self.checkBoxColor_changed)

        self.dockwidget.checkBoxSnap.stateChanged.connect(self.checkBoxSnap_changed)
        self.dockwidget.mQgsSpinBox.valueChanged.connect(self.checkBoxSnap_changed)

        self.map_canvas.setMapTool(self.tool_identify)
        self.last_maptool = self.iface.mapCanvas().mapTool()

        self.dockwidget.checkBoxSmooth.stateChanged.connect(self.checkBoxSmooth_changed)
        self.dockwidget.checkBoxSmooth.setChecked(True)

        self.dockwidget.checkBoxSnap2.stateChanged.connect(self.checkBoxSnap2_changed)
        self.dockwidget.SpinBoxSnap.valueChanged.connect(self.checkBoxSnap2_changed)


    def raster_layer_changed(self):
        self.tool_identify.raster_layer_has_changed(self.dockwidget.mMapLayerComboBox.currentLayer())
        self.checkBoxColor_changed()

    def checkBoxSmooth_changed(self):
        self.tool_identify.smooth_line = (self.dockwidget.checkBoxSmooth.isChecked() is True)

    def checkBoxSnap_changed(self):
        if self.dockwidget.checkBoxSnap.isChecked():
            self.dockwidget.mQgsSpinBox.setEnabled(True)
            snap_tolerance = self.dockwidget.mQgsSpinBox.value()
            self.tool_identify.snap_tolerance_changed(snap_tolerance)
        else:
            self.dockwidget.mQgsSpinBox.setEnabled(False)
            self.tool_identify.snap_tolerance_changed(None)

    def checkBoxSnap2_changed(self):
        if self.dockwidget.checkBoxSnap2.isChecked():
            self.dockwidget.SpinBoxSnap.setEnabled(True)
            snap_tolerance = self.dockwidget.SpinBoxSnap.value()
            self.tool_identify.snap2_tolerance_changed(snap_tolerance)
        else:
            self.dockwidget.SpinBoxSnap.setEnabled(False)
            self.tool_identify.snap2_tolerance_changed(None)


    def turn_off_snap(self):
        self.dockwidget.checkBoxSnap.nextCheckState()

    def checkBoxColor_changed(self):
        if self.dockwidget.checkBoxColor.isChecked():
            self.dockwidget.mColorButton.setEnabled(True)
            self.dockwidget.checkBoxSnap.setEnabled(True)
            color = self.dockwidget.mColorButton.color()
            self.tool_identify.trace_color_changed(color)
        else:
            self.dockwidget.mColorButton.setEnabled(False)
            self.dockwidget.checkBoxSnap.setEnabled(False)
            self.tool_identify.trace_color_changed(False)
