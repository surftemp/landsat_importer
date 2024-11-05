import os
from .optical_formats import OpticalFormats

class LandsatMetadata:

    def __init__(self, metadata, path, optical_format):
        self.metadata = metadata
        self.path = path
        self.optical_format = optical_format

    def set_optical_metadata(self):
        self.optical_units = ""
        self.optical_standard_name = ""
        self.optical_comment = ""
        if self.level == 1:
            if self.optical_format is OpticalFormats.RADIANCE:
                self.optical_units = "W m-2 sr-1 um-1"
                self.optical_standard_name = "toa_outgoing_radiance_per_unit_wavelength"
                self.optical_comment = None
            elif self.optical_format is OpticalFormats.CORRECTED_REFLECTANCE:
                self.optical_units = "1"
                self.optical_standard_name = "toa_bidirectional_reflectance"
                self.optical_comment = None
            elif self.optical_format is OpticalFormats.REFLECTANCE:
                self.optical_units = "1"
                self.optical_standard_name = None
                self.optical_comment = "TOA reflectance without factor for solar zenith angle"
            else:
                raise Exception("Unsupported OLI output format %s" % str(self.optical_format))
        elif self.level == 2:
            self.optical_units = "1"
            self.optical_standard_name = "surface_bidirectional_reflectance"
            self.optical_comment = None

        for band in self.optical_bands:
            self.units[band] = self.optical_units
            if self.optical_standard_name:
                self.standard_names[band] = self.optical_standard_name
            if self.optical_comment:
                self.comments[band] = self.optical_comment

    def get_id(self):
        return f"LANDSAT_SCENE_ID={self.scene_id} LANDSAT_PRODUCT_ID={self.product_id}"

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
                if file == stem + "_" + suffix:
                    band_paths[band] = os.path.join(folder, file)
        return band_paths

    def get_band_number(self, band):
        if band.startswith("B"):
            try:
                return str(int(band[1:]))
            except:
                return None

    def is_integer(self, band):
        return band in ["QA", "QA_PIXEL", "QA_AEROSOL", "QA_RADSAT"]

    def is_level1_angle(self, band):
        return band in ["SAA", "SZA", "VAA", "VZA"]

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

    def get_extent(self, latlon):
        # order "UL", "UR", "LL", "LR"
        latlon = latlon.upper()
        assert latlon in ['LAT', 'LON']
        root = "LANDSAT_METADATA_FILE/PROJECTION_ATTRIBUTES"
        ul = self[root + f"/CORNER_UL_{latlon}_PRODUCT"]
        ur = self[root + f"/CORNER_UR_{latlon}_PRODUCT"]
        ll = self[root + f"/CORNER_LL_{latlon}_PRODUCT"]
        lr = self[root + f"/CORNER_LR_{latlon}_PRODUCT"]
        if ul is None or ur is None or ll is None or lr is None:
            raise Exception("get_lat_extent")
        return [float(ul), float(ur), float(ll), float(lr)]



