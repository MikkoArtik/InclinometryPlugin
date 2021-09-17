import os.path
from typing import List, Tuple, NamedTuple
import webbrowser as wb

import numpy as np

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import QgsVectorLayer, QgsProject

from .resources import *
from .inclinometry_calc_dialog import InclinometryCalcDialog

from .core.dialogs import show_folder_dialog
from .core.dialogs import show_file_dialog

from .core.importing import load_incl_file
from .core.importing import load_points_file
from .core.inclinometry import MD_TYPE, XY_TYPE
from .core.inclinometry import Well

from .core.exporting import create_inclinometry_txt_file
from .core.exporting import create_well_horizontal_trace_shp_file
from .core.exporting import create_points_interpolation_file

from . import qtawesome as qta


HELP_PAGE = 'https://mikkoartik.github.io/InclinometryPlugin/'


class InclinometryCalc:
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
            'i18n', 'InclinometryCalc_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Inclinometry calculator')
        self.dlg = InclinometryCalcDialog()

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

        self.crs_id = 0
        self.export_folder = '/'
        self.processing_type = XY_TYPE
        self.magnetic_declination = 0.0
        self.incl_file_data = np.array([])
        self.incl_file_columns: List[str] = []

        self.points_file_data = []
        self.points_file_columns: List[str] = []

        self.well_head_coords = [0., 0., 0.]
        self.well_name = ''

        self.dlg.bHelp.clicked.connect(self.open_help_page)
        self.dlg.bOpenInclFile.clicked.connect(self.open_incl_file)
        self.dlg.bOpenPointsFile.clicked.connect(self.open_points_file)
        self.dlg.cbProcessingType.currentTextChanged.connect(
            self.set_columns_enabling)
        self.dlg.eOpenFolder.clicked.connect(self.open_export_folder)
        self.dlg.bApply.clicked.connect(self.proc)

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        return QCoreApplication.translate('InclinometryCalc', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True, status_tip=None,
                   whats_this=None, parent=None):
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
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/inclinometry_calc/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Inclinometry calculator'), callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Inclinometry calculator'),
                action)
            self.iface.removeToolBarIcon(action)

    def set_start_form_state(self):
        ui = self.dlg
        ui.cbProcessingType.addItems([XY_TYPE, MD_TYPE])
        ui.eInclFilePath.clear()
        ui.ePointsFilePath.clear()
        ui.eWellName.clear()
        ui.sbXValue.setValue(0)
        ui.sbYValue.setValue(0)
        ui.sbWellHeadAltitude.setValue(0)
        ui.cbDxColumn.clear()
        ui.cbDyColumn.clear()
        ui.cbVerticalDepthColumn.clear()
        ui.cbMDColumn.clear()
        ui.cbInclinationColumn.clear()
        ui.cbAzimuthColumn.clear()
        ui.cbPointColumn.clear()
        ui.cbMDPointColumn.clear()
        ui.sbMagneticAzimuthCorrection.setValue(0)
        ui.eExportFolder.clear()

        self.set_columns_enabling()

    def fill_incl_column_selectors(self, items):
        if len(items) == 0:
            return
        self.dlg.cbDxColumn.addItems(items)
        self.dlg.cbDyColumn.addItems(items)
        self.dlg.cbVerticalDepthColumn.addItems(items)
        self.dlg.cbMDColumn.addItems(items)
        self.dlg.cbAzimuthColumn.addItems(items)
        self.dlg.cbInclinationColumn.addItems(items)

    def fill_points_column_selectors(self, items):
        if len(items) == 0:
            return
        self.dlg.cbPointColumn.addItems(items)
        self.dlg.cbMDPointColumn.addItems(items)

    def set_columns_enabling(self):
        proc_type = self.dlg.cbProcessingType.currentText()
        if proc_type == XY_TYPE:
            self.dlg.cbDxColumn.setEnabled(True)
            self.dlg.cbDyColumn.setEnabled(True)
            self.dlg.cbVerticalDepthColumn.setEnabled(True)
            self.dlg.cbMDColumn.setEnabled(False)
            self.dlg.cbAzimuthColumn.setEnabled(False)
            self.dlg.cbInclinationColumn.setEnabled(False)
            self.processing_type = XY_TYPE
            self.magnetic_declination = 0
            self.dlg.sbMagneticAzimuthCorrection.setEnabled(False)
        elif proc_type == MD_TYPE:
            self.dlg.cbDxColumn.setEnabled(False)
            self.dlg.cbDyColumn.setEnabled(False)
            self.dlg.cbVerticalDepthColumn.setEnabled(False)
            self.dlg.cbMDColumn.setEnabled(True)
            self.dlg.cbAzimuthColumn.setEnabled(True)
            self.dlg.cbInclinationColumn.setEnabled(True)
            self.processing_type = MD_TYPE
            self.dlg.sbMagneticAzimuthCorrection.setEnabled(True)
        else:
            pass

    def get_form_data(self):
        x, y = self.dlg.sbXValue.value(), self.dlg.sbYValue.value()
        z = self.dlg.sbWellHeadAltitude.value()
        self.well_head_coords = [x, y, z]

        coord_id = int(self.dlg.mProjection.crs().authid().split(':')[1])
        self.crs_id = coord_id
        self.magnetic_declination = \
            self.dlg.sbMagneticAzimuthCorrection.value()
        self.well_name = self.dlg.eWellName.text()

    def open_incl_file(self):
        ui = self.dlg
        ui.eInclFilePath.clear()
        ui.cbDxColumn.clear()
        ui.cbDyColumn.clear()
        ui.cbVerticalDepthColumn.clear()
        ui.cbMDColumn.clear()
        ui.cbInclinationColumn.clear()
        ui.cbAzimuthColumn.clear()
        path = show_file_dialog()
        if path is None:
            return

        ui.eInclFilePath.setText(path)
        self.incl_file_columns, self.incl_file_data = load_incl_file(path)
        self.fill_incl_column_selectors(items=self.incl_file_columns)

    def open_points_file(self):
        self.dlg.ePointsFilePath.clear()
        self.dlg.cbPointColumn.clear()
        self.dlg.cbMDPointColumn.clear()
        path = show_file_dialog()
        if path is None:
            return
        self.dlg.ePointsFilePath.setText(path)
        self.points_file_columns, self.points_file_data = load_points_file(
            path)
        self.fill_points_column_selectors(items=self.points_file_columns)

    def open_export_folder(self):
        self.export_folder = show_folder_dialog()
        self.dlg.eExportFolder.setText(self.export_folder)

    def get_used_points_column_indexes(self) -> Tuple[int, int]:
        col_1, col_2 = self.dlg.cbPointColumn, self.dlg.cbMDPointColumn
        return col_1.currentIndex(), col_2.currentIndex()

    def get_used_incl_column_indexes(self) -> List[int]:
        column_indexes = []
        if self.processing_type == XY_TYPE:
            column_indexes.append(self.dlg.cbDxColumn.currentIndex())
            column_indexes.append(self.dlg.cbDyColumn.currentIndex())
            column_indexes.append(
                self.dlg.cbVerticalDepthColumn.currentIndex())
        else:
            column_indexes.append(self.dlg.cbMDColumn.currentIndex())
            column_indexes.append(self.dlg.cbInclinationColumn.currentIndex())
            column_indexes.append(self.dlg.cbAzimuthColumn.currentIndex())
        return column_indexes

    def export_interpolation_data(self, well: Well, export_path: str):
        if len(self.points_file_data) == 0:
            return

        points_data = []
        name_col_index, md_col_index = self.get_used_points_column_indexes()
        for item in self.points_file_data:
            point_name = item[name_col_index]
            md_value = float(item[md_col_index])
            points_data.append((point_name, md_value))

        create_points_interpolation_file(well=well, points_data=points_data,
                                         export_path=export_path)

    def load_vector_layer(self, file_path):
        layer = QgsVectorLayer(file_path, self.well_name, 'ogr')
        if not layer.isValid():
            return
        QgsProject.instance().addMapLayer(layer)

    def proc(self):
        self.get_form_data()
        column_indexes = self.get_used_incl_column_indexes()
        data = self.incl_file_data[:, column_indexes]

        well = Well(self.well_head_coords[0], self.well_head_coords[1],
                    self.well_head_coords[2], self.crs_id,
                    self.magnetic_declination, self.processing_type,
                    data)

        file_name = f'{self.well_name}_{self.processing_type}_inclinometry.txt'
        export_path = os.path.join(self.export_folder, file_name)
        create_inclinometry_txt_file(well=well, output_file=export_path)

        file_name = f'{self.well_name}_{self.processing_type}_hor_trace.shp'
        shp_path = os.path.join(self.export_folder, file_name)
        create_well_horizontal_trace_shp_file(well=well,
                                              well_name=self.well_name,
                                              export_path=shp_path)

        file_name = f'{self.well_name}_{self.processing_type}_Points.dat'
        export_path = os.path.join(self.export_folder, file_name)

        self.export_interpolation_data(well, export_path)

        self.load_vector_layer(shp_path)

    @staticmethod
    def open_help_page():
        wb.open(HELP_PAGE)

    def set_styles(self):
        icon = qta.icon('fa5s.question-circle', color='orange',
                        color_active='blue')
        self.dlg.bHelp.setIcon(icon)

        icon = qta.icon('fa5s.folder-open', color='orange',
                        color_active='blue')
        self.dlg.bOpenInclFile.setIcon(icon)
        self.dlg.bOpenPointsFile.setIcon(icon)
        self.dlg.eOpenFolder.setIcon(icon)

        icon = qta.icon('fa5s.calculator', color='orange',
                        color_active='blue')
        self.dlg.bApply.setIcon(icon)

    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.set_styles()
        self.set_start_form_state()

        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            pass
