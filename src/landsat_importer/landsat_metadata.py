import os
from .oli_formats import OLIFormats

class LandsatMetadata:

    def __init__(self, metadata, path, oli_format):
        self.metadata = metadata
        self.path = path
        self.oli_format = oli_format

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

    def is_level2(self, band):
        return band in ["ST", "ST_QA", "EMIS", "EMSD", "TRAD", "URAD", "DRAD", "ATRAN"]

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


