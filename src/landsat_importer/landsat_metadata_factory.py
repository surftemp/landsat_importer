import os

import xml.dom.minidom
import json

from landsat_importer.landsat_7_metadata import Landsat7Metadata
from landsat_importer.landsat_89_metadata import Landsat89Metadata

class LandsatMetadataFactory:

    @staticmethod
    def create_metadata(scene_path, oli_format):
        """
        LandsatMetadataFactory takes care of some of the complexity of the landsat data products

        Args:
            scene_path: path to a landsat scene (folder, or metadata file)
            oli_format: the output format to use for OLI bands
        """
        path = None
        if os.path.isdir(scene_path):
            for filename in os.listdir(scene_path):
                if filename.lower().endswith("_mtl.xml"):
                    path = os.path.join(scene_path, filename)
        elif os.path.isfile(scene_path):
            ext = os.path.splitext(scene_path)[1]
            if ext in [".txt", ".xml"]:
                path = scene_path
            else:
                raise Exception("input path does not point to a metadata xml file")
        else:
            raise Exception(
                "input path does not point to a metadata xml file or folder containing a landsat scene")

        if path is None:
            raise Exception("No MTL.XML file found in scene")

        if path.endswith('xml'):
            metadata = LandsatMetadataFactory.read_metadata_xml(path)
        else:
            metadata = LandsatMetadataFactory.read_metadata_odl(path)

        spacecraft_id = metadata.get("LANDSAT_METADATA_FILE", {}).get("IMAGE_ATTRIBUTES", {}).get("SPACECRAFT_ID", "")
        if spacecraft_id == "LANDSAT_7":
            return Landsat7Metadata(metadata, path, oli_format=oli_format)
        else:
            return Landsat89Metadata(metadata, path, oli_format=oli_format)

    @staticmethod
    def read_metadata_xml(path):
        metadata = {}
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
            metadata[doc.documentElement.tagName] = v
        return metadata

    @staticmethod
    def read_metadata_odl(path):
        """Read Landsat metadata from ODL format .txt file"""
        metadata = {}
        groups = []
        with open(path) as file:
            for line in file:
                line = line.strip()
                if line == "END":
                    break
                # line should be of form NAME = VALUE
                name, var = line.split(' = ', 1)
                if var.startswith('"') and var.endswith('"'):
                    var = var[1:-1]
                if name == "GROUP":
                    groups.append(var)
                elif name == "END_GROUP":
                    groups = groups[:-1]
                else:
                    m = metadata
                    for group in groups:
                        if group not in m:
                            m[group] = {}
                        m = m[group]
                    m[name] = var
        return metadata


if __name__ == '__main__':
    meta = LandsatMetadataFactory.create_metadata("/home/dev/github/usgs/downloads_l1", "")
    print(json.dumps(meta, indent=4))