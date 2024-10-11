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

"""
Support for parsing landsat8 text formatted metadata (_MTL.txt) files
"""

import datetime
from pytz import UTC
from .oli_formats import OLIFormats
from .landsat_metadata import LandsatMetadata
import logging

# references

# https://www.usgs.gov/media/files/landsat-8-9-olitirs-collection-2-level-1-data-format-control-book
# https://www.usgs.gov/media/files/landsat-8-collection-2-level-2-science-product-guide

suffixes_l1 = {
    "B1" : "B1.TIF",
    "B2" : "B2.TIF",
    "B3" : "B3.TIF",
    "B4" : "B4.TIF",
    "B5" : "B5.TIF",
    "B6" : "B6.TIF",
    "B7" : "B7.TIF",
    "B9" : "B9.TIF",
    "B10" : "B10.TIF",
    "B11" : "B11.TIF",
    "QA" : "BQA.TIF",
    "QA_PIXEL": "QA_PIXEL.TIF",
    "VAA": "VAA.TIF",
    "VZA": "VZA.TIF",
    "SAA": "SAA.TIF",
    "SZA": "SZA.TIF"
}

suffixes_l2 = {
    "B1" : "SR_B1.TIF",
    "B2" : "SR_B2.TIF",
    "B3" : "SR_B3.TIF",
    "B4" : "SR_B4.TIF",
    "B5" : "SR_B5.TIF",
    "B6" : "SR_B6.TIF",
    "B7" : "SR_B7.TIF",
    "ST": "ST_B10.TIF",
    "ST_QA": "ST_QA.TIF",
    "EMIS": "ST_EMIS.TIF",
    "EMSD": "ST_EMSD.TIF",
    "TRAD": "ST_TRAD.TIF",
    "URAD": "ST_URAD.TIF",
    "DRAD": "ST_DRAD.TIF",
    "ATRAN": "ST_ATRAN.TIF",
    "QA_PIXEL": "QA_PIXEL.TIF",
    "QA_AEROSOL": "SR_QA_AEROSOL.TIF",
    "QA_RADSAT": "QA_RADSAT.TIF",
    "MTL" : "MTL.txt"
}

def get_cloud_confidence():
    return lambda q: (q >> 8) & 3

def get_cloud_shadow_confidence():
    return lambda q: (q >> 10) & 3

def get_cirrus_confidence():
    return lambda q: (q >> 14) & 3

product_info = {
    'https://doi.org/10.5066/P975CC9B': {
        'title': 'Landsat 8-9 Operational Land Imager and Thermal Infrared Sensor Collection 2 Level-1 Data',
        'summary': 'Landsat 8-9 Operational Land Imager (OLI) and Thermal Infrared Sensor (TIRS) Collection 2 Level-1 15- to 30-meter multispectral data.',
        },
    'https://doi.org/10.5066/P9OGBGM6': {
        'title': 'Landsat 8-9 OLI/TIRS Collection 2 Level-2 Science Products',
        'summary': 'Landsat 8-9 Operational Land Imager (OLI) and Thermal Infrared (TIRS) Collection 2 Level-2 Science Products 30-meter multispectral data.',
        }
    }


class Landsat89Metadata(LandsatMetadata):

    # https://www.usgs.gov/media/files/landsat-8-9-olitirs-collection-2-level-1-data-format-control-book
    L1C2_QA = [  # (mask,value,meaning)
        (1, 1, "designated_fill"),
        (2, 2, "dilated_cloud"),
        (4, 4, "cirrus"),
        (8, 8, "cloud"),
        (16, 16, "cloud_shadow"),
        (32, 32, "snow"),
        (64, 64, "clear"),
        (128, 64, "water"),
        (768, 0, "no cloud_confidence level set"),
        (768, 256, "low cloud_confidence"),
        (768, 512, "medium cloud_confidence"),
        (768, 768, "high cloud_confidence"),
        (3072, 0, "no cloud_shadow_confidence level set"),
        (3072, 1024, "low cloud_shadow_confidence"),
        (3072, 2048, "medium cloud_shadow_confidence"),
        (3072, 3072, "high cloud_shadow_confidence"),
        (12288, 0, "no snow_ice_confidence level set"),
        (12288, 4096, "low snow_ice_confidence"),
        (12288, 8192, "medium snow_ice_confidence"),
        (12288, 12288, "high snow_ice_confidence"),
        (49152, 0, "not determined cirrus_confidence"),
        (49152, 16384, "low cirrus_confidence"),
        (49152, 32768, "medium cirrus_confidence"),
        (49152, 49152, "high cirrus_confidence"),
    ]

    def __init__(self, metadata, path, oli_format):
        """
        Landsat89Metadata takes care of some of the complexity of the landsat data products

        Args:
            metadata: dictionary containing landsat metadata
            path: path of the xml file that produced the metadata
            oli_format: the output format to use for OLI bands
        """
        super().__init__(metadata, path, oli_format)
        self.logger = logging.getLogger("landsat_89_metadata")

        self.landsat = 0
        self.sensor_id = ""

        if "L1_METADATA_FILE" in self:
            self.collection = 1
            raise Exception("Landsat Collection 1 is not supported")
        elif "LANDSAT_METADATA_FILE" in self:
            self.collection = 2
            self.spacecraft_id = self["LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/SPACECRAFT_ID"]
            self.processing_level = self["LANDSAT_METADATA_FILE/PRODUCT_CONTENTS/PROCESSING_LEVEL"]
            acquisition_date = self["LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/DATE_ACQUIRED"].strip()  # YYYY-MM-DD
            acquisition_time = self["LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/SCENE_CENTER_TIME"][0:8]  # HH:MM:SS
            self.sensor_id = self["LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/SENSOR_ID"]
        else:
            raise Exception("Unable to parse metadata file %s" % self.path)

        self.product_id = self["LANDSAT_METADATA_FILE/PRODUCT_CONTENTS/LANDSAT_PRODUCT_ID"]
        self.scene_id = self["LANDSAT_METADATA_FILE/LEVEL1_PROCESSING_RECORD/LANDSAT_SCENE_ID"]
        self.doi = self['LANDSAT_METADATA_FILE/PRODUCT_CONTENTS/DIGITAL_OBJECT_IDENTIFIER']
        try:
            self.title = product_info[self.doi]['title']
            self.summary = product_info[self.doi]['summary']
        except KeyError:
            self.title = f'{self.spacecraft_id} {self.processing_level} data'
            self.summary = ''
            pass
        self.acknowledgement = self['LANDSAT_METADATA_FILE/PRODUCT_CONTENTS/ORIGIN']
        self.software_l1 = self['LANDSAT_METADATA_FILE/LEVEL1_PROCESSING_RECORD/PROCESSING_SOFTWARE_VERSION']

        self.level = None           # the processing level, 1 or 2
        self.oli_bands = []         # the names of supported optical bands

        if self.processing_level.startswith("L1"):
            self.level = 1
            self.oli_bands = ["B1","B2","B3","B4","B5","B6","B7","B9"] # miss out panchromatic B8 band
        elif self.processing_level.startswith("L2SP"):
            self.level = 2
            self.oli_bands = ["B1","B2","B3","B4","B5","B6","B7"] # OLI bands are 1-7
            self.software_l2 = self['LANDSAT_METADATA_FILE/LEVEL2_PROCESSING_RECORD/PROCESSING_SOFTWARE_VERSION']
        else:
            raise Exception("Unsupported processing level %s" % self.processing_level)

        self.acquisition_timestamp = datetime.datetime.strptime("%s %s" % (acquisition_date, acquisition_time),
                                                                "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        for nr in range(4,10):
            if self.spacecraft_id == "LANDSAT_%d" % nr:
                self.landsat = nr
                break

        if self.landsat != 8 and self.landsat != 9:
            raise Exception("No support for spacecraft_id=%s" % self.spacecraft_id)

        oli_units = ""
        oli_standard_name = ""
        oli_comment = ""

        if self.level == 1:
            if self.oli_format is OLIFormats.RADIANCE:
                oli_units = "W m-2 sr-1 um-1"
                oli_standard_name = "toa_outgoing_radiance_per_unit_wavelength"
                oli_comment = None
            elif self.oli_format is OLIFormats.CORRECTED_REFLECTANCE:
                oli_units = "1"
                oli_standard_name = "toa_bidirectional_reflectance"
                oli_comment = None
            elif self.oli_format is OLIFormats.REFLECTANCE:
                oli_units = "1"
                oli_standard_name = None
                oli_comment = "TOA reflectance without factor for solar zenith angle"
            else:
                raise Exception("Unsupported OLI output format %s" % str(self.oli_format))
        elif self.level == 2:
            oli_units = "1"
            oli_standard_name = "surface_bidirectional_reflectance"
            oli_comment = None

        # fill out the following metadata that describes the input bands and their mapping to output CF-compliant metadata

        self.available_bands = [] # the names of bands in the input data
        self.comments = {} # partial mapping from input band name to a comment in the output variable
        self.names = {} # partial mapping from input band name to a the name of the output variable
        self.standard_names = {} # partial mapping from input band name to the standard_name of the output variable
        self.long_names = {} # partial mapping from input band name to the long_name of the output variable
        self.units = {} # partial mapping from input band name to the units of the output variable

        if self.level == 2:
            self.available_bands = ["B1", "B2", "B3", "B4", "B5", "B6", "B7"]
            self.available_bands += ["ST", "ST_QA", "EMIS", "EMSD", "TRAD", "URAD", "DRAD", "ATRAN",
                                    "QA_PIXEL", "QA_AEROSOL", "QA_RADSAT"]
            self.units["ST"] = "K"
            self.units["ST_QA"] = "K"
            self.units["TRAD"] = "W/(m2.sr.μm)/ DN"
            self.units["URAD"] = "W/(m2.sr.μm)/ DN"
            self.units["DRAD"] = "W/(m2.sr.μm)/ DN"

            self.standard_names["ST"] = "surface_temperature"

        else:
            self.available_bands = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B9", "B10", "B11"]
            self.available_bands.append(self.get_qa_band())

            angle_bands = ["VAA","VZA","SAA","SZA"]
            self.available_bands += angle_bands

            for band in angle_bands:
                self.units[band] = "degree"

            self.names["SZA"] = "solar_zenith_angle"
            self.names["SAA"] = "solar_azimuth_angle"
            self.names["VZA"] = "satellite_zenith_angle"
            self.names["VAA"] = "satellite_azimuth_angle"

            self.standard_names["SZA"] = "solar_zenith_angle"
            self.standard_names["SAA"] = "solar_azimuth_angle"
            self.standard_names["VZA"] = "sensor_zenith_angle"
            self.standard_names["VAA"] = "sensor_azimuth_angle"

            self.long_names["SZA"] = "solar zenith angle"
            self.long_names["SAA"] = "solar azimuth angle"
            self.long_names["VZA"] = "satellite zenith angle"
            self.long_names["VAA"] = "satellite azimuth angle"

            self.comments["VAA"] = "The satellite azimuth angle at the time of the observations"
            self.comments["VZA"] = "The satellite zenith angle at the time of the observations"

            self.units["B10"] = "K"
            self.units["B11"] = "K"

            self.standard_names["B10"] = "toa_brightness_temperature"
            self.standard_names["B11"] = "toa_brightness_temperature"

            self.long_names[self.get_qa_band()] = 'QA Band'
            self.standard_names[self.get_qa_band()] = 'quality_flag'

        for band in self.oli_bands:
            self.units[band] = oli_units
            if oli_standard_name:
                self.standard_names[band] = oli_standard_name
            if oli_comment:
                self.comments[band] = oli_comment

    # level 1 decoding

    def is_level1_bt(self, band):
        return band in ["B10", "B11"]

    def is_level1_radiance(self, band):
        return band in ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B9"] and self.oli_format is OLIFormats.RADIANCE

    def is_level1_reflectance(self, band):
        return band in ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B9"] and self.oli_format is OLIFormats.REFLECTANCE

    def is_level1_corrected_reflectance(self, band):
        return band in ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B9"] and self.oli_format is OLIFormats.CORRECTED_REFLECTANCE

    def get_level1_reflectance_correction(self,band):
        # return (add,mult,sun_elevation)
        add = self[f'LANDSAT_METADATA_FILE/LEVEL1_RADIOMETRIC_RESCALING/REFLECTANCE_ADD_BAND_{self.get_band_number(band)}']
        mult = self[f'LANDSAT_METADATA_FILE/LEVEL1_RADIOMETRIC_RESCALING/REFLECTANCE_MULT_BAND_{self.get_band_number(band)}']
        sun_elevation = self['LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/SUN_ELEVATION']

        if add is None or mult is None:
            raise Exception("get_reflectance_correction")
        else:
            return (float(add), float(mult), float(sun_elevation))

    def get_level1_angle_correction(self):
        # return multiplying factor to convert angle band data to degrees
        # angles are encoded as hundredths of a degree
        return 0.01

    def get_level1_radiance_correction(self,band):
        # return (add,mult)
        root = "LANDSAT_METADATA_FILE/LEVEL1_RADIOMETRIC_RESCALING"
        add = self[root+"/RADIANCE_ADD_BAND_%s" % self.get_band_number(band)]
        mult = self[root+"/RADIANCE_MULT_BAND_%s" % self.get_band_number(band)]

        if add is None or mult is None:
            raise Exception("get_radiance_correction")
        else:
            return (float(add),float(mult))

    def get_level1_bt_correction(self,band):
        # return (k1,k2)
        root = "LANDSAT_METADATA_FILE/LEVEL1_THERMAL_CONSTANTS"
        k1 = self[root+"/K1_CONSTANT_BAND_%s" % self.get_band_number(band)]
        k2 = self[root+"/K2_CONSTANT_BAND_%s" % self.get_band_number(band)]
        if k1 is None or k2 is None:
            raise Exception("get_bt_correction")
        else:
            return (float(k1),float(k2))

    # level 2 decoding

    def get_level2_shift(self,band):
        if band == "ST":
            return 149
        elif band in self.oli_bands:
            return -0.2
        else:
            return 0

    def get_level2_scale(self,band):
        if band == "ST":
            return 0.00341802
        elif band == "ST_QA":
            return 0.01
        elif band in ["EMIS", "EMSD", "ATRAN"]:
            return 0.0001
        elif band in ["TRAD", "URAD", "DRAD"]:
            return 0.001
        elif band in self.oli_bands:
            return 0.0000275
        else:
            return 1

    def get_level2_fillvalue(self,band):
        if band == "ST" or band in self.oli_bands:
            return 0
        elif band == "QA_PIXEL" or band == "QA_AEROSOL":
            return 1
        elif band in ["ST_QA", "EMIS", "EMSD", "ATRAN", "TRAD", "URAD", "DRAD"]:
            return -9999
        else:
            return None

    def get_sensor_id(self):
        return self.sensor_id

    def get_landsat(self):
        return self.landsat

    def get_name(self,band):
        return self.names.get(band,band)

    def get_units(self,band):
        return self.units.get(band,"Unitless")

    def get_standard_name(self,band):
        return self.standard_names.get(band,"")

    def get_long_name(self,band):
        return self.long_names.get(band,"")

    def get_comment(self,band):
        return self.comments.get(band,"")

    def get_spacecraft_id(self):
        return self.spacecraft_id

    def get_processing_level(self):
        return self.processing_level

    def get_acquisition_timestamp(self):
        return self.acquisition_timestamp

    def has_band(self,band):
        return band in self.available_bands

    def get_bands(self):
        return self.available_bands

    def get_band_suffixes(self):
        if self.level == 1:
            return suffixes_l1
        else:
            return suffixes_l2

    def get_collection(self):
        return self.collection

    def get_qa_band(self):
        return "QA_PIXEL"

    def get_qa_flag_metadata(self):
        return zip(*Landsat89Metadata.L1C2_QA)

    def __repr__(self):
        return self.spacecraft_id + ":" + self.processing_level
