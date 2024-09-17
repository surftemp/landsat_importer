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
run_landsat_importer <path_to_landsat_scene_metadata_file> <output_netcdf4_path>
```





