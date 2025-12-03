# -*- coding: utf-8 -*-

#     landsat_importer
#     Copyright (C) 2023-2025  National Centre for Earth Observation (NCEO)
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

import logging
import sys

import landsat_importer

def main():

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("main")

    import argparse
    import os.path
    from .optical_formats import OpticalFormats

    parser = argparse.ArgumentParser(prog='landsat_importer', usage='%(prog)s [options]')
    parser.add_argument('-V', '--version', action='version', version="%(prog)s " + landsat_importer.VERSION)

    parser.add_argument("input_path",help="Specify the path to the input landsat scene, may be a folder or metadata filename")
    parser.add_argument("output_path", help="Specify the output folder or filename")

    parser.add_argument("--bands", nargs="+", help="Provide a list of the bands to import")

    parser.add_argument("--inject-metadata", nargs="+", help="Inject global metadata from one or more key=value pairs", default=[])

    parser.add_argument("--check-version", help="Check the version and fail if there is a mismatch")


    parser.add_argument(
        "--export-optical-as",
        type=OpticalFormats,
        default=OpticalFormats.CORRECTED_REFLECTANCE,
        choices=list(OpticalFormats),
        help="L1 only: specify the output format for the optical bands",
    )

    parser.add_argument(
        "--include-angles",
        action='store_true',
        help="include angle data in the export"
    )

    parser.add_argument(
        "--output-file-pattern",
        metavar="<FILE-PATTERN>",
        help="define a pattern for creating the output file names (set to empty string to just use the input scene name)",
        default="{Y}{m}{d}{H}{M}{S}-NCEO-{level}-{product}-v{collection:0.1f}-fv01.0.nc"
    )

    parser.add_argument("--min-lat", help="Min lat of bounding box to extract", type=float, default=None)
    parser.add_argument("--max-lat", help="Max lat of bounding box to extract", type=float, default=None)
    parser.add_argument("--min-lon", help="Min lon of bounding box to extract", type=float, default=None)
    parser.add_argument("--max-lon", help="Max lon of bounding box to extract", type=float, default=None)

    parser.add_argument("--limit", type=int, help="process only this many scenes", default=None)

    parser.add_argument("--export-int16", nargs=3, metavar=("BAND","SCALE","OFFSET"), action="append", help="export band as int16 with offset and scale", default=[])

    args = parser.parse_args()

    if args.check_version:
        if landsat_importer.VERSION != args.check_version:
            print(f"Version mismatch - actual version: {landsat_importer.VERSION} != expected version: {args.check_version}")
            sys.exit(-1)

    from landsat_importer.processor import Processor
    input_paths = []
    if args.input_path.endswith(".csv"):
        import csv
        with open(args.input_path) as f:
            r = csv.reader(f)
            for line in r:
                input_paths.append(line[0])

    elif os.path.isdir(args.input_path):
        for filename in sorted(os.listdir(args.input_path)):
            if filename.lower().endswith("mtl.xml"):
                input_paths.append(os.path.join(args.input_path,filename))
    else:
        input_paths = [args.input_path]

    logger.info("Found %d scenes to process"%(len(input_paths)))

    idx = 0
    processed = 0
    limit = args.limit

    export_scale_offset = {}
    for export_scale in args.export_int16:
        band = export_scale[0]
        scale = float(export_scale[1])
        offset = float(export_scale[2])
        export_scale_offset[band] = (scale,offset)

    for input_path in input_paths:

        if limit is not None and processed >= limit:
            break

        output_path = args.output_path

        logger.info(f"Processing {idx}: {input_path} -> {output_path}")
        idx += 1
        processed += 1

        try:
            p = Processor(input_path,
                          optical_format=args.export_optical_as)
            target_bands = []
            # collect the target bands.  For bands specified as numbers, add a B prefix
            if args.bands:
                target_bands = args.bands[:]

            if len(input_paths)>1 or not output_path.endswith(".nc"):
                # looks like output_path should specify a directory so
                # create if needed, and append the filename based on the specified pattern
                os.makedirs(output_path,exist_ok=True)
                output_file_path = os.path.join(output_path,p.get_output_filename(args.output_file_pattern))
            else:
                output_file_path = output_path
            if os.path.exists(output_file_path):
                logger.info(f"Output path {output_file_path} already exists, skipping")
                continue
            inject_metadata = {}
            if args.inject_metadata:
                for metadata in args.inject_metadata:
                    kv = metadata.split("=")
                    inject_metadata[kv[0]] = kv[1]

            p.process(target_bands)
            p.export(output_file_path, include_angles=args.include_angles, min_lat=args.min_lat, min_lon=args.min_lon,
                     max_lat=args.max_lat, max_lon=args.max_lon, inject_metadata=inject_metadata,
                     export_scale_offset=export_scale_offset)

        except Exception as ex:
            logger.exception(f"Processing failed for {input_path}: "+str(ex))
            if len(input_paths) == 1:
                # if only processing one scene, re-raise the exception and fail the execution
                # if processing multiple scenes, continue
                raise

if __name__ == '__main__':
    main()
