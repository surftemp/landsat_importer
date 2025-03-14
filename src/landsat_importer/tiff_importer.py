# -*- coding: utf-8 -*-

#     landsat_importer
#     Copyright (C) 2023  National Centre for Earth Observation (NCEO)
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Collection of routines to extract data from the landsat8 geotiff files downloaded from usgs earth explorer"""

import logging
import numpy as np
import math
import rioxarray
import xarray as xr
from pyproj import Transformer


class TiffImporter:

    def __init__(self):
        self.logger = logging.getLogger("tiff_import")

    def latlon_image(self, path):
        da = rioxarray.open_rasterio(path)

        ny, nx = len(da['y']), len(da['x'])
        x, y = np.meshgrid(da['x'], da['y'])
        print(da.spatial_ref.projected_crs_name)

        transformer = Transformer.from_crs(da.spatial_ref.projected_crs_name, "EPSG:4326")
        lat, lon = transformer.transform(x.flatten(), y.flatten())
        lon = np.asarray(lon).reshape((ny, nx))
        lat = np.asarray(lat).reshape((ny, nx))

        return lat, lon

    def import_tiff(self, band, path, is_int):
        """
        Open the TIFF file and store in an array.
        """
        da = rioxarray.open_rasterio(path).squeeze(drop=True)
        encoding = da.encoding

        if '_FillValue' in da.attrs:
            da = da.where(da != da._FillValue)
        elif is_int:
            da = da.astype(np.int32)
        else:
            da = da.astype(np.float32)

        return da, encoding

    @staticmethod
    def DN_to_refl(image_data, M_ro, A_ro):
        # https://landsat.usgs.gov/landsat-8-l8-data-users-handbook-section-5
        """
        Convert the DN to TOA Reflectance as described in primer document.
        NOTE THESE ARE UNCORRECTED FOR SUN ANGLE.
        M_rho = Band-specific multiplicative rescaling factor from the metadata
            (REFLECTANCE_MULT_BAND_x, where x is the band number)
        A_rho = Band-specific additive rescaling factor from the metadata
            (REFLECTANCE_ADD_BAND_x, where x is the band number)
        """

        # M_ro = 2.0E-05
        # A_ro = -0.1
        return (image_data * M_ro) + A_ro

    @staticmethod
    def reflectance_corrected(refl, sun_elev_angle):
        """
        Correct TOA Reflectance (array) for Sun angle as described in primer document.
        sun_elev_angle  = sun elevantion angle (from metadata file) - single number
        sun_zenith_angle = solar zenith angle (90 deg - sun_elev_angle) - single number

        See section 5 of https://www.usgs.gov/media/files/landsat-8-data-users-handbook
        """
        sun_zenith_angle = 90. - sun_elev_angle
        Reflectance_corr = refl / (math.cos(math.radians(sun_zenith_angle)))

        return Reflectance_corr

    @staticmethod
    def DN_to_radiance(image_data, ML, AL):
        """
        Take raw data and convert to TOA Radiance using method described in
        Landsat8 Primer document.

        ML = Band-specific multiplicative rescaling factor from the metadata
        (RADIANCE_MULT_BAND_x, where x is the band number)

        AL =  Band-specific additive rescaling factor from the metadata
        (RADIANCE_ADD_BAND_x, where x is the band number)

        See section 5 of https://www.usgs.gov/media/files/landsat-8-data-users-handbook
        """

        Radiance = image_data * ML
        Radiance += AL

        return Radiance



    @staticmethod
    def Radiance_to_satBT(Radiance, K1, K2):

        """
        Convert TOA Radiance to At-Satellite Brightness Temperature (BT).

        K1 = Band-specific thermal conversion constant from the metadata
        (K1_CONSTANT_BAND_x, where x is the band number, 10 or 11)

        K2 = Band-specific thermal conversion constant from the metadata
        (K2_CONSTANT_BAND_x, where x is the band number, 10 or 11)

        See section 5 of https://www.usgs.gov/media/files/landsat-8-data-users-handbook
        """

        satBT = K1 / Radiance
        satBT += 1.0
        satBT = np.log(satBT)
        satBT = K2 / satBT

        return satBT

    @staticmethod
    def Angle_to_Degrees(image_data, ML):
        """
        Take raw solar/sensor azimuth/zenith angles and convert to degrees

        ML = Band-specific multiplicative rescaling factor from the metadata
        """

        angle_degrees = image_data * ML
        return angle_degrees

    @staticmethod
    def decode(image_data, M, A, FILL):
        """
        Decode L2 surface_temperature etc
        """
        if FILL is not None:
            da = image_data.copy()
            da.data = np.where(image_data == FILL, np.nan, (image_data * M) + A)
            return da
        else:
            return (image_data * M) + A

