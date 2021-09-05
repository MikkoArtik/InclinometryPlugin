import numpy as np

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsPoint, QgsGeometry, QgsField, QgsFields, \
    QgsWkbTypes, QgsVectorFileWriter, QgsCoordinateReferenceSystem, \
    QgsFeature

from core.inclinometry import Well, ColumnIndexes
from core.inclinometry import MD_TYPE


def create_inclinometry_txt_file(well: Well, output_file: str):
    header_columns = ['MD', 'Incl', 'Geo_Az', f'x_GK{well.gk_zone_index}',
                      f'y_GK{well.gk_zone_index}', 'Vert_Depth', 'Altitude']
    column_indexes = [ColumnIndexes.md, ColumnIndexes.incl,
                      ColumnIndexes.az, ColumnIndexes.x_global,
                      ColumnIndexes.y_global, ColumnIndexes.depth,
                      ColumnIndexes.altitude]
    result_arr = np.zeros(
        shape=(well.inclinometry_array.shape[0], len(column_indexes)))
    for i, index in enumerate(column_indexes):
        result_arr[:, i] = well.inclinometry_array[:, index]

    if well.processing_type == MD_TYPE:
        for i in range(result_arr.shape[0]):
            az = result_arr[i, ColumnIndexes.az] - well.total_angle_correction + \
                 well.magnetic_declination
            result_arr[i, ColumnIndexes.az] = well.get_result_azimuth(az)

    meridian_correction = well.meridian_correction
    header = '\t'.join(header_columns)

    with open(output_file, 'w') as f:
        f.write(f'Meridian correction = {meridian_correction}\n')
        f.write(f'Magnetic declination = {well.magnetic_declination}\n')
        np.savetxt(f, result_arr, '%f', '\t', header=header,
                   comments='')


def create_well_horizontal_trace_shp_file(well: Well, well_name: str,
                                          export_path: str):
    xy_points = []
    for record in well.inclinometry_array:
        x, y = record[ColumnIndexes.x_global], record[ColumnIndexes.y_global]
        xy_points.append(QgsPoint(x, y))
    line = QgsGeometry.fromPolyline(xy_points)

    fields = QgsFields()
    fields.append(QgsField('WellName', QVariant.String))

    writer = QgsVectorFileWriter(export_path, 'UTF-8', fields,
                                 QgsWkbTypes.LineString,
                                 QgsCoordinateReferenceSystem(well.gk_crs_id),
                                 'ESRI Shapefile')
    feat = QgsFeature()
    feat.setGeometry(line)
    feat.setAttributes([well_name])
    writer.addFeature(feat)
