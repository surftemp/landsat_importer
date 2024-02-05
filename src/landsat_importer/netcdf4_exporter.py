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
import xarray as xr
import numpy as np
import json
import logging

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


    def export(self,input_path, lats, lons, output_layers, to_path, bounds, include_angles=False,history="",shrink=False):
        """
        Export an imported scene

        Args:
            input_path: the path to the input scene
            lats: 2d array of latitudes for each pixel
            lons: 2d array of longitudes for each pixel
            output_layers: list of (band,array) pairs for each layer to export
            to_path: the path to which netcdf4 data is to be exported
            bounds: tuple of form ((min_lat,min_lon),(max_lat,max_lon))
            include_angles: whether to include simulated SAA,SZA,VAA,VZA (applicable for collection 1)
            history: string to supply the processing history to add to global metadata
            shrink: whether to shrink the exported data to include the area described in the bounds parameter
        """
        dataset = xr.Dataset()

        nlat = lats.shape[0]
        nlon = lats.shape[1]

        ((min_lat,min_lon),(max_lat,max_lon)) = bounds

        dataset.attrs['landsat_importer_version'] = LANDSAT_IMPORTER_VERSION
        dataset.attrs['input_scene'] = os.path.split(input_path)[-1]
        dataset.attrs['platform'] = self.landsat_metadata.get_spacecraft_id()

        acquistion_dt = self.landsat_metadata.get_acquisition_timestamp()
        dataset.attrs['acquisition_time'] = date_format(acquistion_dt)
        dataset.attrs['time_coverage_start'] = date_format(acquistion_dt-datetime.timedelta(seconds=12))
        dataset.attrs['time_coverage_end'] = date_format(acquistion_dt+datetime.timedelta(seconds=12))

        dataset.attrs['processing_level'] = str(self.landsat_metadata.get_processing_level())
        dataset.attrs['collection'] = np.int32(self.landsat_metadata.collection)

        dataset.attrs["geospatial_lat_min"] = min_lat
        dataset.attrs["geospatial_lon_min"] = min_lon
        dataset.attrs["geospatial_lat_max"] = max_lat
        dataset.attrs["geospatial_lon_max"] = max_lon
        dataset.attrs["geospatial_lat_units"] = "degrees north"
        dataset.attrs["geospatial_lon_units"] = "degrees east"

        # dataset.attrs["geospatial_lat_resolution"] = "%d m" % round(resolution_m_lat)
        # dataset.attrs["geospatial_lon_resolution"] = "%d m" % round(resolution_m_lon)
        # dataset.attrs["spatial_resolution"] = "%d m" % round((resolution_m_lat + resolution_m_lon) * 0.5)

        dataset.attrs["cdm_data_type"] = "grid"
        dataset.attrs["history"] = history
        dataset.attrs["acknowledgement"] = "Image courtesy of the U.S. Geological Survey"
        dataset.attrs["date_created"] = date_format(datetime.datetime.now())
        dataset.attrs["sensor"] = dataset.attrs["instrument"] = self.landsat_metadata.get_sensor_id()

        username = "?"
        try:
            username = getpass.getuser()
        except:
            pass

        dataset.attrs["creator_name"] = username
        dataset.attrs["date_created"] = date_format(datetime.datetime.now().astimezone())

        for (key,value) in self.inject_metadata.items():
            dataset.attrs[key] = value

        ecomp = {'zlib': True, 'complevel': 5}
        encodings = {"time": {"units": "seconds since 1978-01-01"}}

        dataset["lat"] = xr.DataArray(data=lats, dims=('nj', 'ni'),
                                      attrs={"units": 'degrees_north', "standard_name": "latitude"})
        dataset["lon"] = xr.DataArray(data=lons, dims=('nj', 'ni'),
                                      attrs={"units": 'degrees_east', "standard_name": "longitude"})
        encodings['lat'] = ecomp
        encodings['lon'] = ecomp

        for (band, data) in output_layers:
            # get metadata to write into the exported variable attributes
            # should be empty string if not relevant or CF-compliant string if applicable
            units = self.landsat_metadata.get_units(band)
            standard_name = self.landsat_metadata.get_standard_name(band)
            comment = self.landsat_metadata.get_comment(band)
            band_name = self.landsat_metadata.get_name(band)
            long_name = self.landsat_metadata.get_long_name(band)

            if self.landsat_metadata.is_integer(band):
                data = data.astype(int)
                encodings[band_name] = {'dtype': 'int32'}
            else:
                encodings[band_name] = {'dtype':'float32'}

            encodings[band_name].update(ecomp)

            data = np.expand_dims(data, axis=0)
            dataset[band_name] = xr.DataArray(data=data, dims=("time", "nj", "ni"))

            if units:
                dataset[band_name].attrs["units"] = units

            if standard_name:
                dataset[band_name].attrs["standard_name"] = standard_name

            if long_name:
                dataset[band_name].attrs["long_name"] = long_name

            if comment:
                dataset[band_name].attrs["comment"] = comment

            if band == self.landsat_metadata.get_qa_band():
                (flag_masks, flag_values, flag_meanings) = self.landsat_metadata.get_qa_flag_metadata()
                # Output datatype may be modified via the encodings dictionary, so
                # need to check both encodings and current array to get correct type
                flag_type = encodings[band_name].get('dtype') or data.dtype
                dataset[band_name].attrs["flag_values"] = np.array(flag_values, flag_type)
                dataset[band_name].attrs["flag_masks"] = np.array(flag_masks, flag_type)
                # Convert flag meanings into valid CF attribute
                dataset[band_name].attrs["flag_meanings"] = ' '.join(s.replace(' ', '_') for s in flag_meanings)

        if include_angles and self.landsat_metadata.get_collection() == 1:
            # for collection 2, angles should already be included via bands SAA,SZA,VAA,VZA converted from TIFFs
            # for collection 1, need to create equivalent but constant per-pixel angles from the metadata
            for name in ["satellite_zenith_angle","relative_azimuth_angle"]:
                da = self.create_dummy_angles(nlat,nlon)
                da.attrs["units"] = "degree"
                if name == "satellite_zenith_angle":
                    da.attrs["long_name"] = "satellite zenith angle"
                    da.attrs["standard_name"] = "sensor_zenith_angle"
                    da.attrs["comment"] = "The satellite zenith angle at the time of the observations"
                elif name == "relative_azimuth_angle":
                    da.attrs["long_name"] = "satellite azimuth angle"
                    da.attrs["standard_name"] = "sensor_azimuth_angle"
                    da.attrs["comment"] = "The relative azimuth angle at the time of the observations"
                dataset[name] = da
                encodings[name] = {'dtype': 'float32'}
                encodings[name].update(ecomp)
            zen, az, dist = self.landsat_metadata.get_solar_angles()
            da = self.create_dummy_angles(nlat, nlon, zen)
            da.attrs = dict(
                long_name='solar zenith angle',
                standard_name='solar_zenith_angle',
                units='degree'
                )
            dataset['solar_zenith_angle'] = da
            encodings['solar_zenith_angle'] = {'dtype': 'float32'}
            encodings['solar_zenith_angle'].update(ecomp)
            da = self.create_dummy_angles(nlat,nlon, az)
            da.attrs = dict(
                long_name='solar azimuth angle',
                standard_name='solar_azimuth_angle',
                units='degree'
                )
            dataset['solar_azimuth_angle'] = da
            encodings['solar_azimuth_angle'] = {'dtype': 'float32'}
            encodings['solar_azimuth_angle'].update(ecomp)

        dataset["time"] = xr.DataArray(data=np.array([self.landsat_metadata.get_acquisition_timestamp()],dtype='datetime64[ns]'), dims=('time'),
                                      attrs={"standard_name": "time", "long_name":"reference time of observations"})


        if shrink:
            self.logger.info(f"Shrinking output to box lon: {min_lon} - {max_lon}, lat: {min_lat} - {max_lat}")
            mask_lon = dataset.lon.where((dataset.lon >= min_lon) & (dataset.lon <= max_lon))
            mask_lat = dataset.lat.where((dataset.lat >= min_lat) & (dataset.lat <= max_lat))
            combined_mask_lat = mask_lat.where(~np.isnan(mask_lon))
            combined_mask_lon = mask_lon.where(~np.isnan(mask_lat))
            njs = [int(combined_mask_lat.argmin(...)["nj"]),int(combined_mask_lat.argmax(...)["nj"])]
            nis = [int(combined_mask_lon.argmin(...)["ni"]),int(combined_mask_lon.argmax(...)["ni"])]
            dataset = dataset.isel(nj=slice(min(njs),max(njs)),ni=slice(min(nis),max(nis)))


        dataset.to_netcdf(to_path, encoding=encodings)
        self.logger.info("Netcdf4 Export complete to %s" % to_path)


    def create_dummy_angles(self, nlat, nlon, fill_value=None):
        if fill_value is None:
            data = np.zeros((1, nlat, nlon), np.float32)
        else:
            data = np.full((1, nlat, nlon), fill_value, np.float32)
        return xr.DataArray(data=data, dims=("time", "nj", "ni"))

