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
routines for outputting regridded data to netcdf4 and png formats
"""

import os
import getpass
import datetime
import logging

import netCDF4
import xarray as xr
from pyproj import Transformer
import numpy as np

from landsat_importer import VERSION as LANDSAT_IMPORTER_VERSION
# YYYY-MM-DDThh:mm:ss<tz>
DATEFORMAT = "%Y-%m-%dT%H:%M:%S%z"

def date_format(dt):
    if dt is None:
        return None
    return dt.strftime(DATEFORMAT)

def date_parse(s):
    if s is None:
        return None
    return datetime.datetime.strptime(s,DATEFORMAT)


class Netcdf4Exporter:

    """Handle the export of regridded landsat data to netcdf4 and PNG"""

    def __init__(self, landsat_metadata, inject_metadata):
        """
        Construct an exporter instance

        Args:
            landsat_metadata: a LandsatMetadata object
            inject_metadata: dictionary to supply additional global metadata to add to exported file
        """
        self.landsat_metadata = landsat_metadata
        self.inject_metadata = inject_metadata
        self.logger = logging.getLogger("Netcdf4Exporter")


    def export(self, input_path, dataset, bands, to_path, history="", add_latlon=True, geo_type='float32'):
        """
        Export an imported scene

        Args:
            input_path: the path to the input scene
            dataset: xarray dataset containing the scene to export
            bands: list of bands in the dataset
            to_path: the path to which netcdf4 data is to be exported
            history: string to supply the processing history to add to global metadata
            add_latlon: calculate and store per-pixel latitude longitude values
            geo_type: storage type for geolocation (x/y and lat/lon coordinates)
        """
        dataset = dataset.expand_dims('time')
        dataset = dataset.rio.write_coordinate_system()

        dataset.x.encoding['dtype'] = geo_type
        dataset.y.encoding['dtype'] = geo_type

        ecomp = {'zlib': True, 'complevel': 5}

        # Calculate pixel longitude, latitudes.
        # Do this after the scene has been clipped.
        if add_latlon:
            self.logger.info("Computing lat/lon mapping")
            transformer = Transformer.from_crs(dataset.spatial_ref.projected_crs_name, "EPSG:4326")
            lat, lon = transformer.transform(*np.meshgrid(dataset.x, dataset.y))
            dataset['lat'] = ('y', 'x'), lat, {'standard_name':'latitude',  'units':'degrees_north'}
            dataset.lat.encoding.update(ecomp, dtype=geo_type)
            dataset['lon'] = ('y', 'x'), lon, {'standard_name':'longitude', 'units':'degrees_east'}
            dataset.lon.encoding.update(ecomp, dtype=geo_type)

        self.logger.info("Starting Netcdf4 Export")
        dataset.attrs['title'] = self.landsat_metadata.title
        dataset.attrs['summary'] = self.landsat_metadata.summary
        dataset.attrs['Conventions'] = 'CF-1.11, ACDD-1.3'
        dataset.attrs["history"] = history

        dataset.attrs['level1_software_version'] = self.landsat_metadata.software_l1
        if hasattr(self.landsat_metadata, 'software_l2'):
            dataset.attrs['level2_software_version'] = self.landsat_metadata.software_l2
        dataset.attrs['landsat_importer_version'] = LANDSAT_IMPORTER_VERSION
        dataset.attrs['netcdf_version_id'] = netCDF4.getlibversion()

        dataset.attrs["date_created"] = date_format(datetime.datetime.now())

        acquistion_dt = self.landsat_metadata.get_acquisition_timestamp()
        dataset.attrs['acquisition_time'] = date_format(acquistion_dt)
        dataset.attrs['time_coverage_start'] = date_format(acquistion_dt-datetime.timedelta(seconds=12))
        dataset.attrs['time_coverage_end'] = date_format(acquistion_dt+datetime.timedelta(seconds=12))

        dataset.attrs['source_file'] = os.path.split(input_path)[-1]
        dataset.attrs['source'] = self.landsat_metadata.get_id()

        dataset.attrs['platform'] = self.landsat_metadata.get_spacecraft_id()
        dataset.attrs["sensor"] = dataset.attrs["instrument"] = self.landsat_metadata.get_sensor_id()
        dataset.attrs['metadata_link'] = self.landsat_metadata.doi
        dataset.attrs['references'] = self.landsat_metadata.doi

        # Get the bounding box. Note this includes the pixel edges, so will be half
        # a pixel larger than the outermost lat/lon positions
        min_lon, min_lat, max_lon, max_lat = dataset.rio.transform_bounds('EPSG:4326')
        dataset.attrs["geospatial_lat_min"] = min_lat
        dataset.attrs["geospatial_lon_min"] = min_lon
        dataset.attrs["geospatial_lat_max"] = max_lat
        dataset.attrs["geospatial_lon_max"] = max_lon
        dataset.attrs["geospatial_lat_units"] = "degrees_north"
        dataset.attrs["geospatial_lon_units"] = "degrees_east"

        # rio.resolution maybe negative depending on direction of coordinate grid
        res = [round(abs(i)) for i in dataset.rio.resolution()]
        dataset.attrs["geospatial_lat_resolution"] = f'{res[1]} {dataset.y.units}'
        dataset.attrs["geospatial_lon_resolution"] = f'{res[0]} {dataset.x.units}'
        # dataset.attrs["spatial_resolution"] = "%d m" % round((resolution_m_lat + resolution_m_lon) * 0.5)

        dataset.attrs['processing_level'] = str(self.landsat_metadata.get_processing_level())
        dataset.attrs['collection'] = np.int32(self.landsat_metadata.collection)
        dataset.attrs["cdm_data_type"] = "grid"

        dataset.attrs["acknowledgement"] = "Image courtesy of the U.S. Geological Survey"

        username = "?"
        try:
            username = getpass.getuser()
        except:
            pass

        dataset.attrs["creator_name"] = username

        for (key,value) in self.inject_metadata.items():
            dataset.attrs[key] = value



        for band in bands:
            if add_latlon:
                dataset[band].attrs['coordinates'] = 'lon lat'

            if self.landsat_metadata.is_integer(band):
                dataset[band].encoding.update({'dtype': 'int32', "_FillValue": -999})
            else:
                dataset[band].encoding.update({'dtype':'float32'})

            dataset[band].encoding.update(ecomp)

        # Rename variables to use common netCDF names
        nmap = {b:self.landsat_metadata.get_name(b) for b in bands}
        dataset = dataset.rename(nmap)

        dataset["time"] = xr.DataArray(data=np.array([self.landsat_metadata.get_acquisition_timestamp()],dtype='datetime64[ns]'), dims=('time'),
                                      attrs={"standard_name": "time", "long_name":"reference time of observations"})
        dataset.time.encoding.update(dtype='int32', units='seconds since 1978-01-01')


        dataset.to_netcdf(to_path)
        self.logger.info("Netcdf4 Export complete to %s" % to_path)



