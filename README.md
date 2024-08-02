# landsat_importer

import landsat 8/9 scenes to netcdf4 

## Installation


```
git clone git@github.com:surftemp/landsat_importer.git
cd landsat_importer
conda create -n rioxarray_env python=3.11
conda activate rioxarray_env
conda install rioxarray netcdf4 rasterio pandas pyproj scipy
pip install -e .
```

## Example Usage

Convert a single landsat scene, all bands

```
run_landsat_importer <path_to_landsat_scene_metadata_file> <output_netcdf4_path>
```





