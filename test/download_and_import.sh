#!/bin/bash

mamba activate usgs_env

export USGS_USERNAME=nmccarroll
export USGS_TOKEN='_8l8uttTHjdA0kFXYT20aG1q0Ja!YYG1i4HjLXG9ogP!Edj7FKN1UpJZE06_5EfE'

# search for scenes in a region and time period of interest
usgs search-create LANDSAT_OT_C2_L1 search.json \
      --noninteractive --lat-min -20.91 --lon-min 150.83 --lat-max -20.68 --lon-max 151.16 --start-date 2025-01-01 --end-date 2025-03-31 --max-cloud-cover 10
usgs search-run search.json > scenes.csv

# download the scenes
usgs_download --filename scenes.csv --output-folder outputs --file-suffixes QA_PIXEL.TIF B2.TIF B3.TIF B4.TIF xml

mamba deactivate

# import the scenes using landsat_importer
mamba activate landsat_importer_env

# use scale of 0.001 and offset 0 for B2/B3/B4
landsat_importer outputs imported 

mamba deactivate
