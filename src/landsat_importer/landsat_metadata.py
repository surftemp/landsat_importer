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
import os
import logging
import xml.dom.minidom

suffixes_l1 = {
    "1" : "B1.TIF",
    "2" : "B2.TIF",
    "3" : "B3.TIF",
    "4" : "B4.TIF",
    "5" : "B5.TIF",
    "6" : "B6.TIF",
    "7" : "B7.TIF",
    "8" : "B8.TIF",
    "9" : "B9.TIF",
    "10" : "B10.TIF",
    "11" : "B11.TIF",
    "QA" : "BQA.TIF",
    "MTL" : "MTL.txt",
    "QA_PIXEL": "QA_PIXEL.TIF",
    "VAA": "VAA.TIF", # collection 2 only
    "VZA": "VZA.TIF", # collection 2 only
    "SAA": "SAA.TIF", # collection 2 only
    "SZA": "SZA.TIF"  # collection 2 only
}

suffixes_l2 = {
    "1" : "SR_B1.TIF",
    "2" : "SR_B2.TIF",
    "3" : "SR_B3.TIF",
    "4" : "SR_B4.TIF",
    "5" : "SR_B5.TIF",
    "6" : "SR_B6.TIF",
    "7" : "SR_B7.TIF",
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

def get_cloud_confidence(collection):
    if collection == 1:
        return lambda q: (q >> 5) & 3
    else:
        return lambda q: (q >> 8) & 3

def get_cloud_shadow_confidence(collection):
    if collection == 1:
        return lambda q: (q >> 7) & 3
    else:
        return lambda q: (q >> 10) & 3

def get_cirrus_confidence(collection):
    if collection == 1:
        return lambda q: (q >> 11) & 3
    else:
        return lambda q: (q >> 14) & 3




class LandsatMetadata:
    # https://www.usgs.gov/media/files/landsat-8-data-users-handbook P55

    L1C1_QA = [ # (mask,value,meaning)
        (1, 1, "designated_fill"),
        (2, 2, "terrain_occlusion"),
        (12, 0, "no bands_radiometric_saturation"),
        (12, 4, "1-2 bands_radiometric_saturation"),
        (12, 8, "3-4 bands_radiometric_saturation"),
        (12, 12, ">=5 bands_radiometric_saturation"),
        (16, 16, "cloud"),
        (96, 0, "not determined cloud_confidence"),
        (96, 32, "low cloud_confidence"),
        (96, 64, "medium cloud_confidence"),
        (96, 96, "high cloud_confidence"),
        (384, 0, "not determined cloud_shadow_confidence"),
        (384, 128, "low cloud_shadow_confidence"),
        (384, 256, "medium cloud_shadow_confidence"),
        (384, 384, "high cloud_shadow_confidence"),
        (1536, 0, "not determined snow_ice_confidence"),
        (1536, 512, "low snow_ice_confidence"),
        (1536, 1024, "medium snow_ice_confidence"),
        (1536, 1536, "high snow_ice_confidence"),
        (6144, 0, "not determined cirrus_confidence"),
        (6144, 2048, "low cirrus_confidence"),
        (6144, 4096, "medium cirrus_confidence"),
        (6144, 6144, "high cirrus_confidence"),
    ]

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


    def __init__(self, scene_path, oli_format):
        """
        LandsatMetadata takes care of some of the complexity of the landsat data products

        Args:
            scene_path: path to a landsat scene (folder, or metadata file)
            oli_format: the output format to use for OLI bands
        """
        self.logger = logging.getLogger("landsat_metadata")
        self.metadata = {}
        self.oli_format = oli_format
        self.path = ""
        if os.path.isdir(scene_path):
            for filename in os.listdir(scene_path):
                if filename.lower().endswith("_mtl.xml"):
                    self.path = os.path.join(scene_path,filename)
                    break
            if not self.path:
                for filename in os.listdir(scene_path):
                    if filename.lower().endswith("_mtl.txt"):
                        self.path = os.path.join(scene_path, filename)
                        break
        elif os.path.isfile(scene_path):
            ext = os.path.splitext(scene_path)[1]
            if ext in [".xml",".txt"]:
                self.path = scene_path
            else:
                raise Exception("input path does not point to a metadata (txt or xml) file")
        else:
            raise Exception(
                "input path does not point to a metadata (txt or xml) file or folder containing a landsat scene")

        if not self.path:
            raise Exception("No MTL.TXT/XML file found in scene")

        self.__read_metadata(self.path)
        self.landsat = 0
        self.sensor_id = ""

        if "L1_METADATA_FILE" in self:
            self.collection = 1
            self.spacecraft_id = self["L1_METADATA_FILE/PRODUCT_METADATA/SPACECRAFT_ID"]
            self.processing_level = self["L1_METADATA_FILE/PRODUCT_METADATA/DATA_TYPE"]
            acquisition_date = self["L1_METADATA_FILE/PRODUCT_METADATA/DATE_ACQUIRED"].strip()  # YYYY-MM-DD
            acquisition_time = self["L1_METADATA_FILE/PRODUCT_METADATA/SCENE_CENTER_TIME"][0:8]  # HH:MM:SS
            self.sensor_id = self["L1_METADATA_FILE/PRODUCT_METADATA/SENSOR_ID"]
        elif "LANDSAT_METADATA_FILE" in self:
            self.collection = 2
            self.spacecraft_id = self["LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/SPACECRAFT_ID"]
            self.processing_level = self["LANDSAT_METADATA_FILE/PRODUCT_CONTENTS/PROCESSING_LEVEL"]
            acquisition_date = self["LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/DATE_ACQUIRED"].strip()  # YYYY-MM-DD
            acquisition_time = self["LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/SCENE_CENTER_TIME"][0:8]  # HH:MM:SS
            self.sensor_id = self["LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES/SENSOR_ID"]
        else:
            raise Exception("Unable to parse metadata file %s" % path)

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

        if self.landsat != 8 and self.landsat != 9:
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
        self.names = {} # partial mapping from input band name to a the name of the output variable
        self.standard_names = {} # partial mapping from input band name to the standard_name of the output variable
        self.long_names = {} # partial mapping from input band name to the long_name of the output variable
        self.units = {} # partial mapping from input band name to the units of the output variable

        if self.processing_level == "L2SP":
            numeric_bands = ["1", "2", "3", "4", "5", "6", "7"]
            self.available_bands += numeric_bands
            self.available_bands += ["ST", "ST_QA", "EMIS", "EMSD", "TRAD", "URAD", "DRAD", "ATRAN",
                                    "QA_PIXEL", "QA_AEROSOL", "QA_RADSAT"]
            self.units["ST"] = "K"
            self.units["ST_QA"] = "K"
            self.units["TRAD"] = "W/(m2.sr.μm)/ DN"
            self.units["URAD"] = "W/(m2.sr.μm)/ DN"
            self.units["DRAD"] = "W/(m2.sr.μm)/ DN"

            self.standard_names["ST"] = "surface_temperature"

        else:
            numeric_bands = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
            self.available_bands += numeric_bands
            self.available_bands.append(self.get_qa_band())

            if self.collection == 2:

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

            self.units["10"] = "K"
            self.units["11"] = "K"

            self.standard_names["10"] = "toa_brightness_temperature"
            self.standard_names["11"] = "toa_brightness_temperature"

        # for input bands identified by a number, prepend "B" to provide the output name
        for numeric_band in numeric_bands:
            self.names[numeric_band] = "B" + numeric_band

        for band in oli_bands:
            self.units[band] = oli_units
            if oli_standard_name:
                self.standard_names[band] = oli_standard_name
            if oli_comment:
                self.comments[band] = oli_comment

    def get_path(self):
        """
        get the path to the metadata file

        Returns:
            path to the metadata file that was read.
        """
        return self.path

    def scan(self, bands, band_suffixes):
        """
        locate the files in the same folder as the metadata file corresponding to requested bands

        Args:
            bands: a list of band names requested
            band_suffixes: a dict mapping from band name to the suffix of the file with the data for the band

        Returns:
            dict: mapping from band name to the path of its file

        Raises:
             Exception if multiple matches exist for a given band
        """
        splits = os.path.split(self.path)
        folder = splits[0]
        metadata_filename = splits[1]
        stem = metadata_filename[:metadata_filename.lower().find("_mtl")] # remove training _MTL*, get a stem which all scene files should match

        files = sorted(os.listdir(folder))
        band_paths = {}
        for file in files:
            for band in bands:
                suffix = band_suffixes[band]
                if file.startswith(stem) and file.endswith(suffix):
                    if band in band_paths:
                        self.logger.warning("Found multiple TIF files with same suffix %s for band %s, ignoring %s"% (suffix,band,file))
                    band_paths[band] = os.path.join(folder, file)
        return band_paths

    def is_bt(self, band):
        return band in ["10", "11"]

    def is_radiance(self, band):
        return band in ["1", "2", "3", "4", "5", "6", "7", "8", "9"] and self.oli_format is OLIFormats.RADIANCE

    def is_reflectance(self, band):
        return band in ["1", "2", "3", "4", "5", "6", "7", "8", "9"] and self.oli_format is OLIFormats.REFLECTANCE

    def is_corrected_reflectance(self, band):
        return band in ["1", "2", "3", "4", "5", "6", "7", "8", "9"] and self.oli_format is OLIFormats.CORRECTED_REFLECTANCE

    def is_integer(self, band):
        return band in ["QA", "QA_PIXEL", "QA_AEROSOL", "QA_RADSAT"]

    def is_angle(self, band):
        return band in ["SAA", "SZA", "VAA", "VZA"]

    def get_solar_angles(self):
        if self.collection == 1:
            root = "L1_METADATA_FILE/IMAGE_ATTRIBUTES"
        else:
            root = "LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES"

        elev = self[root+"/SUN_ELEVATION"]
        azim = self[root+"/SUN_AZIMUTH"]
        dist = self[root+"/EARTH_SUN_DISTANCE"]
        return 90-float(elev), float(azim), float(dist)

    def get_reflectance_correction(self,band):
        # return (add,mult,sun_elevation)
        if self.collection == 2:
            root = "LANDSAT_METADATA_FILE/LEVEL1_RADIOMETRIC_RESCALING"
        else:
            root = "L1_METADATA_FILE/RADIOMETRIC_RESCALING"
        add = self[root+"/REFLECTANCE_ADD_BAND_%s" % band]
        mult = self[root+"/REFLECTANCE_MULT_BAND_%s" % band]

        if self.collection == 2:
            root = "LANDSAT_METADATA_FILE/IMAGE_ATTRIBUTES"
        else:
            root = "L1_METADATA_FILE/IMAGE_ATTRIBUTES"
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
        if self.collection == 2:
            root = "LANDSAT_METADATA_FILE/LEVEL1_RADIOMETRIC_RESCALING"
        else:
            root = "L1_METADATA_FILE/RADIOMETRIC_RESCALING"
        add = self[root+"/RADIANCE_ADD_BAND_%s" % band]
        mult = self[root+"/RADIANCE_MULT_BAND_%s" % band]

        if add is None or mult is None:
            raise Exception("get_radiance_correction")
        else:
            return (float(add),float(mult))

    def get_bt_correction(self,band):
        # return (k1,k2)
        if self.collection == 2:
            root = "LANDSAT_METADATA_FILE/LEVEL1_THERMAL_CONSTANTS"
        else:
            root = "L1_METADATA_FILE/TIRS_THERMAL_CONSTANTS"
        k1 = self[root+"/K1_CONSTANT_BAND_%s" % band]
        k2 = self[root+"/K2_CONSTANT_BAND_%s" % band]
        if k1 is None or k2 is None:
            raise Exception("get_bt_correction")
        else:
            return (float(k1),float(k2))

    def get_thermal_lines_samples(self):
        if self.collection == 2:
            root = "LANDSAT_METADATA_FILE/PROJECTION_ATTRIBUTES"
        else:
            root = "L1_METADATA_FILE/PRODUCT_METADATA"
        thermal_lines = self[root + "/THERMAL_LINES"]
        thermal_samples = self[root + "/THERMAL_SAMPLES"]
        return (int(thermal_lines), int(thermal_samples))

    def get_extent(self,is_lat):
        # order "UL", "UR", "LL", "LR"
        if self.collection == 2:
            root = "LANDSAT_METADATA_FILE/PROJECTION_ATTRIBUTES"
        else:
            root = "L1_METADATA_FILE/PRODUCT_METADATA"
        lat_or_lon = "LAT" if is_lat else "LON"
        ul = self[root + "/CORNER_UL_%s_PRODUCT" % lat_or_lon]
        ur = self[root + "/CORNER_UR_%s_PRODUCT" % lat_or_lon]
        ll = self[root + "/CORNER_LL_%s_PRODUCT" % lat_or_lon]
        lr = self[root + "/CORNER_LR_%s_PRODUCT" % lat_or_lon]
        if ul is None or ur is None or ll is None or lr is None:
            raise Exception("get_lat_extent")
        return [float(ul),float(ur),float(ll),float(lr)]

    def is_level2(self, band):
        return band in ["ST", "ST_QA", "EMIS", "EMSD", "TRAD", "URAD", "DRAD", "ATRAN"]

    def get_level2_shift(self,band):
        # https://www.usgs.gov/media/files/landsat-8-collection-2-level-2-science-product-guide
        if band == "ST":
            root = "LANDSAT_METADATA_FILE/LEVEL2_SURFACE_TEMPERATURE_PARAMETERS"
            return float(self[root+"/TEMPERATURE_ADD_BAND_ST_B10"])  # 149
        else:
            return 0

    def get_level2_scale(self,band):
        # https://www.usgs.gov/media/files/landsat-8-collection-2-level-2-science-product-guide
        if band == "ST":
            root = "LANDSAT_METADATA_FILE/LEVEL2_SURFACE_TEMPERATURE_PARAMETERS"
            return float(self[root + "/TEMPERATURE_MULT_BAND_ST_B10"])  # 0.00341802
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
        if band == "ST":
            return 0
        elif band in ["ST_QA", "EMIS", "EMSD", "ATRAN", "TRAD", "URAD", "DRAD"]:
            return -9999
        else:
            return None

    def get_surface_temperature_correction(self):
        root = "LANDSAT_METADATA_FILE/LEVEL2_SURFACE_TEMPERATURE_PARAMETERS"
        mult = self[root+"/TEMPERATURE_MULT_BAND_ST_B10"] # 0.00341802
        add = self[root+"/TEMPERATURE_ADD_BAND_ST_B10"] # 149.0
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

    def get_pixel_filter(self, cloud_filter, cloud_shadow_filter, cirrus_filter):

        if not cloud_filter and not cloud_shadow_filter and not cirrus_filter:
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
        cirrus_threshold = get_threshold(cirrus_filter)

        cloud_confidence = get_cloud_confidence(self.collection)
        cloud_shadow_confidence = get_cloud_shadow_confidence(self.collection)
        cirrus_confidence = get_cirrus_confidence(self.collection)

        def filter_function(q):
            if cloud_confidence(q) >= cloud_threshold:
                return False
            if cloud_shadow_confidence(q) >= cloud_shadow_threshold:
                return False
            if cirrus_confidence(q) >= cirrus_threshold:
                return False
            return True

        return filter_function

    def get_qa_band(self):
        if self.collection == 1:
            return "QA"
        elif self.collection == 2:
            return "QA_PIXEL"

    def get_qa_flag_metadata(self):
        if self.collection == 1:
            return zip(*LandsatMetadata.L1C1_QA)
        else:
            return zip(*LandsatMetadata.L1C2_QA)

    def __read_metadata(self, path):
        if path.endswith(".txt"):
            groups = []
            with open(path) as file:
                for line in file:
                    line = line.strip()
                    if line == "END":
                        break
                    # line should be of form NAME = VALUE
                    idx = line.find(" = ")
                    name = line[:idx]
                    var = line[idx + 3:]
                    if var.startswith('"') and var.endswith('"'):
                        var = var[1:-1]
                    if name == "GROUP":
                        groups.append(var)
                    elif name == "END_GROUP":
                        groups = groups[:-1]
                    else:
                        m = self.metadata
                        for group in groups:
                            if group not in m:
                                m[group] = {}
                            m = m[group]
                        m[name] = var
        elif path.endswith(".xml"):
            with open(path) as file:
                doc = xml.dom.minidom.parseString(file.read())

                def parse(ele):
                    value = {}
                    text = ""
                    for child in ele.childNodes:
                        if child.nodeType == child.ELEMENT_NODE:
                            value[child.tagName] = parse(child)
                        elif child.nodeType == child.TEXT_NODE:
                            text += child.nodeValue
                    if len(value):
                        return value
                    else:
                        return text

                v = parse(doc.documentElement)
                self.metadata[doc.documentElement.tagName] = v


    def __getitem__(self, keys):
        """
        keys may be supplied as a tuple or '/' separated string e.g.
            self["L1_METADATA_FILE", "PRODUCT_METADATA", "SPACECRAFT_ID"]
            self["L1_METADATA_FILE/PRODUCT_METADATA/SPACECRAFT_ID"]

        Also supports two special characters
            . will match the first group
            * will match any except the last group
        Example:
            self["./PRODUCT_METADATA/SPACECRAFT_ID"]
            self["*/SPACECRAFT_ID"]
        """
        if isinstance(keys, str):
            keys = keys.split('/')
        m = self.metadata
        if keys[0] == '*' and len(keys) == 2:
            # Recursive function to find any matching key
            def find_key(d, k):
                if k in d:
                    return d[k]
                else:
                    for v in d.values():
                        if isinstance(v, dict):
                            i = find_key(v, k)
                            if i:
                                return i
            return find_key(m, keys[1])
        for key in keys:
            if key == '.':
                m = next(iter(m.values()))
            elif key in m:
                m = m[key]
            else:
                return None
        return m

    def __contains__(self, key):
        if self[key]:
            return True

    def __repr__(self):
        return self.spacecraft_id + ":" + self.processing_level
