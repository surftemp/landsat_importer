#!/bin/bash

mamba deactivate
mamba activate usgs_env

export USGS_USERNAME=<username>
export USGS_TOKEN=<token>

usgs search-create LANDSAT_OT_C2_L1 search.json \
      --noninteractive --lat-min -20.91 --lon-min 150.83 --lat-max -20.68 --lon-max 151.16 --start-date 2025-01-01 --end-date 2025-01-31 --max-cloud-cover 10

usgs search-run search.json > scenes.csv

usgs_download --filename scenes.csv --output-folder outputs --file-suffixes B2.TIF B3.TIF B4.TIF .XML

mamba deactivate
mamba activate landsat_importer_env

landsat_importer outputs imported