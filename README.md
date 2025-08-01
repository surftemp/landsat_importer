# landsat_importer

import landsat 7/8/9 scenes to netcdf4 

## Installation

Installation into a miniforge enviromnent is suggested.  See [https://github.com/conda-forge/miniforge](https://github.com/conda-forge/miniforge) for installing miniforge.

Create a miniforge environment called landsat_importer_env using:

```
mamba create -n landsat_importer_env python=3.11
mamba activate landsat_importer_env
mamba install rioxarray netcdf4 rasterio pandas pyproj scipy
```

Install this tool into the environment using:

```
git clone git@github.com:surftemp/landsat_importer.git
cd landsat_importer
pip install -e .
```

## Example Usage

Convert a single landsat scene, all bands

```
landsat_importer <input-path> <output-path>
```

Where:

<input-path> EITHER the path of the downloaded landsat metadata file (.xml or .txt) or a folder containing multiple landsat scenes
<output-path> EITHER the output path of the netcdf4 file to write or the path to an output folder

## Command line options

| option                                     | description                                                                                                                             | example                                                                                                 |
|--------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| --bands                                    | provide a list of bands to import                                                                                                       | --bands B2 B3 B4                                                                                        |
 | --include-angles                           | include angle data                                                                                                                      | --include-angles                                                                                        |
 | --output-file-pattern                      | specify a pattern for naming the output file                                                                                            | default is --output-file-pattern {Y}{m}{d}{H}{M}{S}-NCEO-{level}-{product}-v{collection:0.1f}-fv01.0.nc |
 | --min-lat, --max-lat, --min-lon, --max-lon | define a bounding box for importing the scene                                                                                           | --min-lat 50 --max-lat 50.5 --min-lon -0.5 --max-lon 0                                                  |
 | --limit                                    | when processing an input folder, stop after processing this many scenes                                                                 | --limit 5                                                                                               |
 | --export-optical-as                        | choose how to import optical data, one of "corrected_reflectance" (default), "reflectance", "radiance"                                  | --export-optical-as "radiance"                                                                          |
 | --export-int16                             | store a band using int16 values, using the provided the band name, scale factor and offset.  This option needs to be used for each band | --export-int16 B4 0.001 0                                                                               |

The `--export-int16` option can be very useful in compressing the output data.  However, the tool will check that the values within the band lie within the range that can be safely compressed and if not, will disable compression, displaying the following message

```
$ landsat_importer outputs imported --export-int16 B2 0.001 0 --export-int16 B3 0.001 0 --export-int16 B4 0.001 0
NFO:main:Found 1 scenes to process
INFO:main:Processing 0: outputs/LC08_L1TP_209048_20250131_20250208_02_T1_MTL.xml -> imported
...
WARNING:Netcdf4Exporter:Band B2 requested int16 encoding using (scale=1e-05,offset=0.0) would overflow (data range=(0.11235591024160385,0.5257744789123535), encoded_range=(-0.32767,0.32767) and is not enabled
INFO:Netcdf4Exporter:Netcdf4 Export complete to imported/20250131115127-NCEO-L1C-Landsat8-v2.0-fv01.0.nc
```

A safe encoding for reflectance bands would be (scale_factor=0.001,offset=0) retaining 3 decimal places of accuracy.

## Usage in conjunction with the `usgs` and `usgs-download` tools

The [USGS tools](https://github.com/surftemp/usgs) can be used to locate and download Landsat Imagery.  

An [example script](test/download_and_import.sh) that demonstrates using the USGS tools to download imagery and then landsat_importer to decode and convert them to netcdf4.

## Known issues

https://www.usgs.gov/landsat-missions/landsat-collection-2-known-issues

## Version History

| version | changes                                                                                |
|---------|----------------------------------------------------------------------------------------|
 | 0.0.1   | initial version                                                                        |
 | 0.0.2   | add support for Landsat 7                                                              |
 | 0.0.3   | rename `--export_optical_as` to `--export-optical-as`, remove `--offset` and `--batch` |
 | 0.0.4   | add `--export-int16`                                                                   |




