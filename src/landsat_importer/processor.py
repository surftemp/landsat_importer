# -*- coding: utf-8 -*-

#    landsat_importer
#    Copyright (C) 2023  National Centre for Earth Observation (NCEO)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Main subroutine for processing landsat data, API entrypoint"""
import enum

import xarray

from landsat_importer.landsat_metadata import LandsatMetadata, OLIFormats
from landsat_importer import VERSION
from landsat_importer.tiff_importer import TiffImporter
from landsat_importer.netcdf4_exporter import Netcdf4Exporter

import numpy as np
import os
import gc
import time
import logging

class Processor:
    """
    The main class for coordinating the regridding of a single landsat scene
    """

    # prevent PIL complaining about "zip bombs" (?) when asked to open large tiff files
    # Image.MAX_IMAGE_PIXELS = 10000000000

    # the number of m per degree of latitude
    M_PER_DEGREE_LATLON = 111111



    def __init__(self, input_path,
                 oli_format=OLIFormats.CORRECTED_REFLECTANCE):
        """
        Construct a Processor

        Args:
            input_folder: the folder containing the input scene
            oli_format: specify how to export the OLI bands, should be an OLIFormats enum value
        """
        self.input_path = input_path
        self.logger = logging.getLogger("Processor")

        self.importer = TiffImporter()
        self.oli_format = oli_format

        self.target_bands = []

        # load up metadata for this scene
        self.landsat_metadata = LandsatMetadata(input_path, oli_format=oli_format)

        # find the paths associated with the various bands that could exist in this scene
        # note that the input folder may not contain all the expected files
        self.band_paths = self.landsat_metadata.scan(bands=self.landsat_metadata.get_bands(),
                                                band_suffixes=self.landsat_metadata.get_band_suffixes())

        self.logger.info("Read metadata: "+str(self.landsat_metadata))

        self.lats = self.lons = None
        self.output_layers = []
        self.min_lon = self.max_lon = self.min_lat = self.max_lat = None

    def check_bands(self, target_bands):
        """
        Check that a list of target bands are available in the scene being processed.  If they are not,
        remove from the list of target bands and print a warning

        Args:
            target_bands: a list of requested band names
        """
        for band in target_bands[:]:
            if band not in self.band_paths:
                self.logger.warning("requested band %s not found in input scene, skipping" % (band))
                target_bands.remove(band)

    def process(self, target_bands=[]):
        """
        Process a set of bands from the scene

        Args:
            target_bands: a list of requested bands, for example ["3","4","5","11","QA"]
            output_path: path for the exported netcdf4 file

        Returns:
            an xarray.Dataset
        """
        start_time = time.time()
        self.logger.info("landsat_importer version %s" % (VERSION))
        self.target_bands = target_bands

        if len(self.target_bands) == 0:
            self.target_bands = self.landsat_metadata.get_bands()

        # get lon/lat min/max from scene metadata

        lats = self.landsat_metadata.get_extent(is_lat=True)
        lons = self.landsat_metadata.get_extent(is_lat=False)

        # work out the bounding box
        self.min_lon = min(lons)
        self.max_lon = max(lons)
        self.min_lat = min(lats)
        self.max_lat = max(lats)

        self.logger.info("Acquired at " + str(self.landsat_metadata.get_acquisition_timestamp()))

        self.logger.info("Computing lat/lon mapping")
        # TODO ensure not band 8

        self.lats, self.lons = self.importer.latlon_image(self.band_paths[self.target_bands[0]])

        for band in self.target_bands:
            gc.collect()
            self.logger.info("Processing band %s" % (band))

            # get the data imported from TIFF format
            band_data = self.importer.import_tiff(band, self.band_paths[band],
                                             self.landsat_metadata.is_integer(band))

            # decode pixel values according to the encoding parameters stored in the
            # landsat metadata
            processed_band_data = self.preprocess_band(self.landsat_metadata, band, band_data)
            self.output_layers.append((band,processed_band_data))

        end_time = time.time()
        return end_time - start_time

    def preprocess_band(self,landsat_metadata, band, data):
        """
        preprocess a particular band to extract pixel values from the landsat encoding

        Args:
            landsat_metadata: a LandsatMetadata object
            band: the name of the band
            data: a numpy array containing the band's data imported from the landsat scene

        Returns:

        """
        if landsat_metadata.is_level2(band):
            add = landsat_metadata.get_level2_shift(band)
            mult = landsat_metadata.get_level2_scale(band)
            fill = landsat_metadata.get_level2_fillvalue(band)
            return TiffImporter.decode(data, mult, add, fill)
        else:
            if landsat_metadata.is_reflectance(band) or landsat_metadata.is_corrected_reflectance(band):
                data = np.where(data == 0.0, np.nan, data)
                A_rho, M_rho, sun_elevation = landsat_metadata.get_reflectance_correction(band)
                refl = TiffImporter.DN_to_refl(data, M_rho, A_rho)
                if landsat_metadata.is_corrected_reflectance(band):
                    return TiffImporter.reflectance_corrected(refl, sun_elevation)
                else:
                    return refl
            elif landsat_metadata.is_bt(band) or landsat_metadata.is_radiance(band):
                data = np.where(data == 0.0, np.nan, data)
                AL, ML = landsat_metadata.get_radiance_correction(band)
                rad = TiffImporter.DN_to_radiance(data, ML, AL)
                if landsat_metadata.is_bt(band):
                    K1, K2 = landsat_metadata.get_bt_correction(band)
                    return TiffImporter.Radiance_to_satBT(rad, K1, K2)
                else:
                    return rad
            elif landsat_metadata.is_angle(band):
                ML = landsat_metadata.get_angle_correction()
                return TiffImporter.Angle_to_Degrees(data, ML)
            else:
                # do nothing
                return data

    def get_output_filename(self, pattern):
        """
        Get the output filename based on a filename pattern that contains the following codes:
          {Y} 4 digit year
          {y} 2 digit year
          {m} 2 digit month
          {d} 2 digit day of month
          {H} 2 digit hour
          {M} 2 digit minute
          {S} 2 digit second
          {collection} Landsat collection
          {product} Product code (e.g. Landsat8)
          {level} Processing level

        Args:
            pattern: file pattern containing any/all of the above codes

        Returns:
            filename based on the pattern with codes replaced by data from the scene's
            acquistion time

        """
        md = self.landsat_metadata
        subs = dict((f, md.get_acquisition_timestamp().strftime('%'+f)) for f in 'yYmdHMS')
        subs['collection'] = md.collection
        subs['product'] = f'Landsat{md.landsat}'
        subs['level'] = 'L1C' if md.level == 1 else md.processing_level
        return pattern.format(**subs)

    def get_landsat_metadata(self):
        """
        Get metadata loaded from the scene being processed

        Returns:
            A LandsatMetadata object

        """
        return self.landsat_metadata

    def export(self, output_path, include_angles=False, history="", min_lat=None, min_lon=None, max_lat=None, max_lon=None):
        """
        Export the regridded scene

        Args:
            output_path: the path to which the scene is written in netcdf4 format
            include_angles: include angle variables in the exported netcdf4 file
            history: a string which summarises the processing parameters
        """
        self.logger.info("Exporting output grid to file %s" % output_path)

        exporter = Netcdf4Exporter(self.get_landsat_metadata())

        shrink = False
        if min_lat is None:
            min_lat = self.min_lat
        elif min_lat < self.min_lat:
            self.logger.warning("specified bounding box outside scene")
            min_lat = self.min_lat
        else:
            shrink = True

        if max_lat is None:
            max_lat = self.max_lat
        elif max_lat > self.max_lat:
            self.logger.warning("specified bounding box outside scene")
            max_lat = self.max_lat
        else:
            shrink = True

        if min_lon is None:
            min_lon = self.min_lon
        elif min_lon < self.min_lon:
            self.logger.warning("specified bounding box outside scene")
            min_lon = self.min_lon
        else:
            shrink = True

        if max_lon is None:
            max_lon = self.max_lon
        elif max_lon > self.max_lon:
            self.logger.warning("specified bounding box outside scene")
            max_lon = self.max_lon
        else:
            shrink = True



        exporter.export(input_path=self.input_path, lats=self.lats, lons=self.lons, output_layers=self.output_layers,
                        bounds=((min_lat,min_lon),(max_lat,max_lon)), include_angles=include_angles,
                        history=history,to_path=output_path,shrink=shrink)
