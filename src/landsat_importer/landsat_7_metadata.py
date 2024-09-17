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

# see also https://www.usgs.gov/landsat-missions/landsat-7

# https://esajournals.onlinelibrary.wiley.com/doi/full/10.1002/ecy.1730
# https://www.usgs.gov/faqs/what-are-band-designations-landsat-satellites

# the keys are the band numbers for Landsat 7


suffixes_l1 = {
    "B1" : "B1.TIF",
    "B2" : "B2.TIF",
    "B3" : "B3.TIF",
    "B4" : "B4.TIF",
    "B5" : "B5.TIF",
    "B6_1" : "B6_VCID_1.TIF",
    "B6_2" : "B6_VCID_2.TIF",
    "B7" : "B7.TIF",
    "B8" : "B8.TIF",
    "MTL" : "MTL.txt",
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
    "ST": "ST_B6.TIF",
    "ST_QA": "ST_QA.TIF",
    "EMIS": "ST_EMIS.TIF",
    "EMSD": "ST_EMSD.TIF",
    "TRAD": "ST_TRAD.TIF",
    "URAD": "ST_URAD.TIF",
    "DRAD": "ST_DRAD.TIF",
    "ATRAN": "ST_ATRAN.TIF",
    "QA_PIXEL": "QA_PIXEL.TIF",
    "QA_AEROSOL": "",
    "QA_RADSAT": "QA_RADSAT.TIF",
    "MTL" : "MTL.txt"
}

def get_cloud_confidence():
    return lambda q: (q >> 8) & 3

def get_cloud_shadow_confidence():
    return lambda q: (q >> 10) & 3

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

class Landsat7Metadata(LandsatMetadata):
    # https://www.usgs.gov/media/files/landsat-8-data-users-handbook P55

    # https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/media/files/LSDS-1337_Landsat7ETM-C2-L2-DFCB-v6.pdf
    L1C2_QA = [  # (mask,value,meaning)
        (1, 1, "designated_fill"),
        (2, 2, "dilated_cloud"),
        (4, 4, "unused"),
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
        (49152, 0, "unused"),
        (49152, 16384, "unused"),
        (49152, 32768, "unused"),
        (49152, 49152, "unused"),
    ]


    def __init__(self, metadata, path, oli_format):
        """
        Landsat7Metadata takes care of some of the complexity of the landsat data products

        Args:
            metadata: dictionary containing landsat metadata
            path: path of the xml file that produced the metadata
            oli_format: the output format to use for OLI bands
        """
        super().__init__(metadata, path, oli_format)
        self.logger = logging.getLogger("landsat7_metadata")

        self.landsat = 0
        self.sensor_id = ""

        if "L1_METADATA_FILE" in self:
            self.collection = 1
            raise Exception("Collection1 is not supported")
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

        # FIXME
        self.title = f'{self.spacecraft_id} {self.processing_level} data'
        self.summary = ''

        self.acknowledgement = self['LANDSAT_METADATA_FILE/PRODUCT_CONTENTS/ORIGIN']
        self.software_l1 = self['LANDSAT_METADATA_FILE/LEVEL1_PROCESSING_RECORD/PROCESSING_SOFTWARE_VERSION']

        if self.processing_level.startswith("L1"):
            self.level = 1
            oli_bands = [str(b) for b in range(1,10)] # OLI bands are 1-9
        elif self.processing_level.startswith("L2SP"):
            self.level = 2
            oli_bands = [str(b) for b in range(1,8)] # OLI bands are 1-7
        else:
            raise Exception("Unsupported processing level %s" % self.processing_level)

        self.acquisition_timestamp = datetime.datetime.strptime("%s %s" % (acquisition_date, acquisition_time),
                                                                "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        for nr in range(4,10):
            if self.spacecraft_id == "LANDSAT_%d" % nr:
                self.landsat = nr
                break

        if self.landsat != 8 and self.landsat != 9 and self.landsat != 7:
            raise Exception("No support for spacecraft_id=%s" % self.spacecraft_id)

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
        self.names = {} # partial mapping from input band name to the name of the output variable
        self.standard_names = {} # partial mapping from input band name to the standard_name of the output variable
        self.long_names = {} # partial mapping from input band name to the long_name of the output variable
        self.units = {} # partial mapping from input band name to the units of the output variable

        if self.processing_level == "L2SP":
            self.available_bands = [ "B1", "B2", "B3", "B4", "B5"]
            self.available_bands += ["ST", "ST_QA", "EMIS", "EMSD", "TRAD", "URAD", "DRAD", "ATRAN",
                                    "QA_PIXEL", "QA_AEROSOL", "QA_RADSAT"]
            self.units["ST"] = "K"
            self.units["ST_QA"] = "K"
            self.units["TRAD"] = "W/(m2.sr.μm)/ DN"
            self.units["URAD"] = "W/(m2.sr.μm)/ DN"
            self.units["DRAD"] = "W/(m2.sr.μm)/ DN"

            self.standard_names["ST"] = "surface_temperature"

        else:
            self.available_bands = ["B1", "B2", "B3", "B4", "B5", "B6_1", "B6_2", "B7", "B8"]
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

            self.units["B6_1"] = "K"
            self.units["B6_2"] = "K"

            self.standard_names["10"] = "toa_brightness_temperature"
            self.standard_names["11"] = "toa_brightness_temperature"



        for band in oli_bands:
            self.units[band] = oli_units
            if oli_standard_name:
                self.standard_names[band] = oli_standard_name
            if oli_comment:
                self.comments[band] = oli_comment

    def get_band_number(self, band):
        if band == "B6_1":
            return "6_VCID_1"
        elif band == "B6_2":
            return "6_VCID_2"
        else:
            return super().get_band_number(band)

    def is_bt(self, band):
        return band in ["B6_1", "B6_2"]

    def is_radiance(self, band):
        return band in ["B1", "B2", "B3", "B4", "B5", "B7", "B8"] and self.oli_format is OLIFormats.RADIANCE

    def is_reflectance(self, band):
        return band in ["B1", "B2", "B3", "B4", "B5", "B7", "B8"] and self.oli_format is OLIFormats.REFLECTANCE

    def is_corrected_reflectance(self, band):
        return band in ["B1", "B2", "B3", "B4", "B5", "B7", "B8"] and self.oli_format is OLIFormats.CORRECTED_REFLECTANCE

    def get_solar_angles(self):
        root = "LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES"

        elev = self[root+"/SUN_ELEVATION"]
        azim = self[root+"/SUN_AZIMUTH"]
        dist = self[root+"/EARTH_SUN_DISTANCE"]
        return 90-float(elev), float(azim), float(dist)

    def get_reflectance_correction(self,band):
        # return (add,mult,sun_elevation)

        root = "LANDSAT_METADATA_FILE/LEVEL1_RADIOMETRIC_RESCALING"

        add = self[root+"/REFLECTANCE_ADD_BAND_%s" % self.get_band_number(band)]
        mult = self[root+"/REFLECTANCE_MULT_BAND_%s" % self.get_band_number(band)]

        root = "LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES"

        sun_elevation = self[root+"/SUN_ELEVATION"]
        if add is None or mult is None:
            raise Exception("get_reflectance_correction")
        else:
            return (float(add), float(mult), float(sun_elevation))

    def get_angle_correction(self):
        # return multiplying factor to convert angle band data to degrees
        # angles are encoded as hundredths of a degree
        return 0.01

    def get_radiance_correction(self,band):
        # return (add,mult)

        root = "LANDSAT_METADATA_FILE/LEVEL1_RADIOMETRIC_RESCALING"
        add = self[root+"/RADIANCE_ADD_BAND_%s" % self.get_band_number(band)]
        mult = self[root+"/RADIANCE_MULT_BAND_%s" % self.get_band_number(band)]

        if add is None or mult is None:
            raise Exception("get_radiance_correction")
        else:
            return (float(add),float(mult))

    def get_bt_correction(self,band):
        # return (k1,k2)

        root = "LANDSAT_METADATA_FILE/LEVEL1_THERMAL_CONSTANTS"

        k1 = self[root+"/K1_CONSTANT_BAND_%s" % self.get_band_number(band)]
        k2 = self[root+"/K2_CONSTANT_BAND_%s" % self.get_band_number(band)]
        if k1 is None or k2 is None:
            raise Exception("get_bt_correction")
        else:
            return (float(k1),float(k2))

    def get_thermal_lines_samples(self):
        root = "LANDSAT_METADATA_FILE/PROJECTION_ATTRIBUTES"
        thermal_lines = self[root + "/THERMAL_LINES"]
        thermal_samples = self[root + "/THERMAL_SAMPLES"]
        return (int(thermal_lines), int(thermal_samples))

    def get_extent(self,is_lat):
        # order "UL", "UR", "LL", "LR"
        root = "LANDSAT_METADATA_FILE/PROJECTION_ATTRIBUTES"
        lat_or_lon = "LAT" if is_lat else "LON"
        ul = self[root + "/CORNER_UL_%s_PRODUCT" % lat_or_lon]
        ur = self[root + "/CORNER_UR_%s_PRODUCT" % lat_or_lon]
        ll = self[root + "/CORNER_LL_%s_PRODUCT" % lat_or_lon]
        lr = self[root + "/CORNER_LR_%s_PRODUCT" % lat_or_lon]
        if ul is None or ur is None or ll is None or lr is None:
            raise Exception("get_lat_extent")
        return [float(ul),float(ur),float(ll),float(lr)]

    def get_level2_shift(self,band):
        # https://www.usgs.gov/media/files/landsat-8-collection-2-level-2-science-product-guide
        if band == "ST":
            root = "LANDSAT_METADATA_FILE/LEVEL2_SURFACE_TEMPERATURE_PARAMETERS"
            return float(self[root+"/TEMPERATURE_ADD_BAND_ST_B6"])  # 149
        else:
            return 0

    def get_level2_scale(self,band):
        # https://www.usgs.gov/media/files/landsat-8-collection-2-level-2-science-product-guide
        if band == "ST":
            root = "LANDSAT_METADATA_FILE/LEVEL2_SURFACE_TEMPERATURE_PARAMETERS"
            return float(self[root + "/TEMPERATURE_MULT_BAND_ST_B6"])  # 0.00341802
        elif band == "ST_QA":
            return 0.01
        elif band in ["EMIS", "EMSD", "ATRAN"]:
            return 0.0001
        elif band in ["TRAD", "URAD", "DRAD"]:
            return 0.001
        else:
            return 1

    def get_level2_fillvalue(self,band):
        # https://www.usgs.gov/media/files/landsat-8-collection-2-level-2-science-product-guide
        if band in ["ST_QA", "EMIS", "EMSD", "ATRAN", "TRAD", "URAD", "DRAD"]:
            return -9999
        else:
            return 0

    def get_surface_temperature_correction(self):
        root = "LANDSAT_METADATA_FILE/LEVEL2_SURFACE_TEMPERATURE_PARAMETERS"
        mult = self[root+"/TEMPERATURE_MULT_BAND_ST_B6"] # 0.00341802
        add = self[root+"/TEMPERATURE_ADD_BAND_ST_B6"] # 149.0
        if mult is None or add is None:
            raise Exception("get_surface_temperature_correction")
        return [float(add),float(mult)]

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

    def get_pixel_filter(self, cloud_filter, cloud_shadow_filter, cirrus_filter=None):

        if not cloud_filter and not cloud_shadow_filter:
            return None

        def get_threshold(filter):
            if filter == "medium":
                return 2
            elif filter == "high":
                return 3
            else:
                return 4 # allow all values through

        cloud_threshold = get_threshold(cloud_filter)
        cloud_shadow_threshold = get_threshold(cloud_shadow_filter)

        cloud_confidence = get_cloud_confidence()
        cloud_shadow_confidence = get_cloud_shadow_confidence()

        def filter_function(q):
            if cloud_confidence(q) >= cloud_threshold:
                return False
            if cloud_shadow_confidence(q) >= cloud_shadow_threshold:
                return False
            return True

        return filter_function

    def get_qa_band(self):
        return "QA_PIXEL"

    def get_qa_flag_metadata(self):
        return zip(*Landsat7Metadata.L1C2_QA)

    def __repr__(self):
        return self.spacecraft_id + ":" + self.processing_level
