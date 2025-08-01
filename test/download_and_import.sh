#!/bin/bash

mamba deactivate
mamba activate usgs_env

export USGS_USERNAME=<username>
export USGS_TOKEN=<token>

# search for scenes in a region and time period of interest
usgs search-create LANDSAT_OT_C2_L1 search.json \
      --noninteractive --lat-min -20.91 --lon-min 150.83 --lat-max -20.68 --lon-max 151.16 --start-date 2025-01-01 --end-date 2025-01-31 --max-cloud-cover 10
usgs search-run search.json > scenes.csv

# download the scenes
usgs_download --filename scenes.csv --output-folder outputs --file-suffixes B2.TIF B3.TIF B4.TIF .XML

mamba deactivate

# import the scenes using landsat_importer
mamba activate landsat_importer_env

landsat_importer outputs imported

# optional - make true colour plots from the imported scenes (see https://github.com/surftemp/netcdf_explorer for installation details)
# add the scene time to the plot

mamba deactivate

mamba activate netcdfexplorer_env

bigplot --input-path imported/* --input-variable B4 B3 B2 --attrs acquisition_time --output-path plots