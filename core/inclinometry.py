from typing import NamedTuple
from math import cos, sin, radians

import numpy as np

from qgis.core import QgsCoordinateReferenceSystem
from qgis.core import QgsCoordinateTransform
from qgis.core import QgsCoordinateTransformContext


WGS84_ID = 4326
PULKOVO1942_ID = 4284
MD_TYPE, XY_TYPE = 'MD', 'XYZ'


class ColumnIndexes(NamedTuple):
    md = 0
    incl = 1
    az = 2
    x_local = 3
    y_local = 4
    depth = 5
    altitude = 6
    x_global = 7
    y_global = 8

    @property
    def size(self) -> int:
        return 9


class DataTypeError(Exception):
    pass


class Well:
    def __init__(self, x: float, y: float, altitude: float,
                 crs_id: int, magnetic_declination: float,
                 processing_type: str, inclination_data: np.ndarray):
        self.__well_head = (x, y, altitude)
        self.__crs_id = crs_id

        if processing_type not in (MD_TYPE, XY_TYPE):
            raise DataTypeError('Invalid inclination type')
        self.__processing_type = processing_type

        if processing_type == MD_TYPE:
            self.__magnetic_declination = magnetic_declination
        else:
            self.__magnetic_declination = 0

        self.__incl_data = np.zeros(shape=(inclination_data.shape[0],
                                           ColumnIndexes.size))
        if processing_type == MD_TYPE:
            self.__incl_data[:, ColumnIndexes.md] = inclination_data[:, 0]
            self.__incl_data[:, ColumnIndexes.incl] = inclination_data[:, 1]
            self.__incl_data[:, ColumnIndexes.az] = inclination_data[:, 2]
        else:
            self.__incl_data[:, ColumnIndexes.x_local] = inclination_data[:, 0]
            self.__incl_data[:, ColumnIndexes.y_local] = inclination_data[:, 1]
            self.__incl_data[:, ColumnIndexes.depth] = inclination_data[:, 2]
        self.__incl_data[0, ColumnIndexes.altitude] = altitude

        self.__gk_zone_index = self.get_gk_zone_index()
        self.__gk_crs_id = self.get_gk_crs_id()

        self.processing()

    @staticmethod
    def get_src(crs_id: int) -> QgsCoordinateReferenceSystem:
        return QgsCoordinateReferenceSystem(crs_id)

    @staticmethod
    def get_result_azimuth(az_value) -> float:
        az_value %= 360
        if az_value >= 0:
            return az_value
        else:
            return 360 + az_value

    def get_middle_angle(self, alpha: float, beta: float) -> float:
        if abs(alpha - beta) <= 180:
            return (alpha + beta) / 2
        result = min(alpha, beta) - (360 - abs(alpha - beta)) / 2
        return self.get_result_azimuth(result)

    def transform_xy_coordinates(self, x: float, y: float, source_crs_id: int,
                                 target_crs_id: int) -> tuple:
        if source_crs_id == target_crs_id:
            return x, y
        crs_src = self.get_src(source_crs_id)
        crs_target = self.get_src(target_crs_id)
        ctx = QgsCoordinateTransformContext()
        transform = QgsCoordinateTransform(crs_src, crs_target, ctx)
        projection = transform.transform(x, y)
        return projection.x(), projection.y()

    def get_gk_zone_index(self) -> int:
        x, _ = self.transform_xy_coordinates(
            self.__well_head[0], self.__well_head[1], self.__crs_id,
            PULKOVO1942_ID)
        return int((x + 6) / 6)

    def get_gk_crs_id(self) -> int:
        return 28400 + self.get_gk_zone_index()

    @property
    def processing_type(self) -> str:
        return self.__processing_type

    @property
    def magnetic_declination(self) -> float:
        return self.__magnetic_declination

    @property
    def gk_zone_index(self) -> int:
        return self.__gk_zone_index

    @property
    def gk_crs_id(self) -> int:
        return self.__gk_crs_id

    @property
    def meridian_correction(self) -> float:
        gk_zone_index = self.gk_zone_index
        central_meridian = 6 * gk_zone_index - 3
        x, y = self.transform_xy_coordinates(self.__well_head[0],
                                             self.__well_head[1],
                                             self.__crs_id, PULKOVO1942_ID)
        return (x - central_meridian) * sin(radians(y))

    @property
    def total_angle_correction(self) -> float:
        return self.magnetic_declination - self.meridian_correction

    def calc_inclinometry_by_md(self):
        arr = self.__incl_data
        for i in range(arr.shape[0]):
            az = arr[i, ColumnIndexes.az] + self.total_angle_correction
            az = self.get_result_azimuth(az)
            arr[i, ColumnIndexes.az] = az

        x_gk_head, y_gk_head = self.transform_xy_coordinates(
                self.__well_head[0], self.__well_head[1], self.__crs_id,
                self.gk_crs_id)
        arr[0, ColumnIndexes.x_global] = x_gk_head
        arr[0, ColumnIndexes.y_global] = y_gk_head
        for i in range(1, arr.shape[0]):
            mid_az = self.get_middle_angle(arr[i - 1, ColumnIndexes.az],
                                           arr[i, ColumnIndexes.az])
            mid_incl = (arr[i, ColumnIndexes.incl] +
                        arr[i - 1, ColumnIndexes.incl]) / 2
            delta_md = arr[i, ColumnIndexes.md] - arr[i - 1, ColumnIndexes.md]
            mid_az = radians(mid_az)
            mid_incl = radians(mid_incl)

            dx = delta_md * sin(mid_incl) * sin(mid_az)
            dy = delta_md * sin(mid_incl) * cos(mid_az)
            dz = delta_md * cos(mid_incl)

            x_local = arr[i - 1, ColumnIndexes.x_local] + dx
            y_local = arr[i - 1, ColumnIndexes.y_local] + dy
            depth = arr[i - 1, ColumnIndexes.depth] + dz

            arr[i, ColumnIndexes.x_local] = x_local
            arr[i, ColumnIndexes.y_local] = y_local
            arr[i, ColumnIndexes.x_global] = x_local + x_gk_head
            arr[i, ColumnIndexes.y_global] = y_local + y_gk_head

            arr[i, ColumnIndexes.depth] = depth
            arr[i, ColumnIndexes.altitude] = self.__well_head[2] - depth

    def calc_inclinometry_by_xyz(self):
        arr = self.__incl_data

        x0, y0 = arr[0, ColumnIndexes.x_local], arr[0, ColumnIndexes.y_local]
        z0 = arr[0, ColumnIndexes.depth]
        arr[:, ColumnIndexes.x_local] -= x0
        arr[:, ColumnIndexes.y_local] -= y0
        arr[:, ColumnIndexes.depth] -= z0

        x_gk_head, y_gk_head = self.transform_xy_coordinates(
            self.__well_head[0], self.__well_head[1], self.__crs_id,
            self.gk_crs_id)
        arr[0, ColumnIndexes.x_global] = x_gk_head
        arr[0, ColumnIndexes.y_global] = y_gk_head

        rotate_angle = radians(self.meridian_correction)
        for i in range(1, arr.shape[0]):
            dx = arr[i, ColumnIndexes.x_local] - arr[i - 1, ColumnIndexes.x_local]
            dy = arr[i, ColumnIndexes.y_local] - arr[i - 1, ColumnIndexes.y_local]
            dz = arr[i, ColumnIndexes.depth] - arr[i - 1, ColumnIndexes.depth]
            delta_md = (dx ** 2 + dy ** 2 + dz ** 2) ** 0.5
            arr[i, ColumnIndexes.md] = arr[i - 1, ColumnIndexes.md] + delta_md

            dx_old = arr[i, ColumnIndexes.x_local]
            dy_old = arr[i, ColumnIndexes.y_local]
            dx_new = dx_old * cos(rotate_angle) - dy_old * sin(rotate_angle)
            dy_new = dx_old * sin(rotate_angle) + dy_old * cos(rotate_angle)

            arr[i, ColumnIndexes.x_global] = x_gk_head + dx_new
            arr[i, ColumnIndexes.y_global] = y_gk_head + dy_new
            arr[i, ColumnIndexes.altitude] = self.__well_head[2] - arr[i, ColumnIndexes.depth]

    def processing(self):
        if self.__processing_type == MD_TYPE:
            self.calc_inclinometry_by_md()
        else:
            self.calc_inclinometry_by_xyz()

    @property
    def inclinometry_array(self) -> np.ndarray:
        return self.__incl_data

    def interpolate_data(self, md_value: float) -> np.ndarray:
        min_md = np.min(self.inclinometry_array[:, ColumnIndexes.md])
        max_md = np.max(self.inclinometry_array[:, ColumnIndexes.md])
        if not min_md <= md_value <= max_md:
            return np.array([])

        column_indexes = [ColumnIndexes.md, ColumnIndexes.x_global,
                          ColumnIndexes.y_global, ColumnIndexes.depth,
                          ColumnIndexes.altitude]

        top_index, bottom_index = 0, 0
        for i in range(self.inclinometry_array.shape[0]):
            if self.inclinometry_array[i, ColumnIndexes.md] < md_value:
                top_index = i
            elif self.inclinometry_array[i, ColumnIndexes.md] == md_value:
                top_index, bottom_index = i, i
                break
            else:
                bottom_index = i
                break

        if top_index == bottom_index:
            return self.inclinometry_array[top_index, column_indexes]

        min_md = self.inclinometry_array[top_index, ColumnIndexes.md]
        max_md = self.inclinometry_array[bottom_index, ColumnIndexes.md]
        linear_coeff = (md_value - min_md) / (max_md - min_md)
        diff_arr = self.inclinometry_array[bottom_index] - self.inclinometry_array[top_index]
        return linear_coeff * diff_arr + self.inclinometry_array[top_index]
