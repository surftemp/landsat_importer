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

import logging
import random
import json

available = False
try:
    from pyjob import use
    use("slurm")

    import pyjob
    available = True
except:
    pass

slurm_defaults = {
    'runtime': '04:00',
    'memlimit': '4192',
    'queue': 'short-serial',
    'name': 'landsat_importer'
}

def main():

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("main")

    import argparse
    import os.path
    from .oli_formats import OLIFormats

    parser = argparse.ArgumentParser()

    parser.add_argument("input_path",help="Specify the path to the input landsat scene, may be a folder or metadata filename")
    parser.add_argument("output_path", help="Specify the output folder or filename")

    parser.add_argument("--bands", help="Provide a comma separated list of the bands to export", default="")

    parser.add_argument("--inject-metadata", nargs="+", help="Inject global metadata from one or more key=value pairs", default=[])

    parser.add_argument(
        "--export_oli_as",
        type=OLIFormats,
        default=OLIFormats.CORRECTED_REFLECTANCE,
        choices=list(OLIFormats),
        help="L1 only: specify the output format for the OLI bands 1-9",
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
    parser.add_argument("--use-slurm", action="store_true", help="do not run locally, instead launch slurm job(s)")

    parser.add_argument("--limit", type=int, help="process only this many scenes", default=None)
    parser.add_argument("--offset", type=int, help="start processing at this offset in the list", default=None)
    parser.add_argument("--batch", type=int, help="use this batch  size", default=None)

    args = parser.parse_args()

    rng = random.Random(123)

    slurm_options = None
    if args.use_slurm:
        slurm_options = {k: v for (k, v) in slurm_defaults.items()}

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

    rng.shuffle(input_paths)

    logger.info("Found %d scenes to process"%(len(input_paths)))

    idx = 0
    processed = 0
    offset = args.offset
    limit = args.limit
    batch = args.batch

    for input_path in input_paths:
        if offset is not None and idx < offset:
            idx += 1
            continue
        if limit is not None and processed >= limit:
            break

        output_path = args.output_path
        if batch is not None:
            batch_nr = idx // batch
            output_path = os.path.join(output_path, str(batch_nr))

        logger.info(f"Processing {idx}: {input_path} -> {output_path}")
        idx += 1
        processed += 1

        if slurm_options:
            script_contents = "conda activate rioxarray_env\n\n"
            script_contents += f"run_landsat_importer {input_path} {output_path} --bands {args.bands}"
            if args.min_lat:
                script_contents += f" --min-lat {args.min_lat}"
                script_contents += f" --max-lat {args.max_lat}"
                script_contents += f" --min-lon {args.min_lon}"
                script_contents += f" --max-lon {args.max_lon}"
            if args.include_angles:
                script_contents += " --include-angles"
            if args.inject_metadata:
                s = "".join(args.inject_metadata)
                script_contents += f" --inject-metadata {s}"
            script_contents += f" --export_oli_as {args.export_oli_as}"
            script_contents += f" --output-file-pattern \"{args.output_file_pattern}\"\n"
            job = pyjob.Job('hostname', script=script_contents, options=slurm_options, env="/bin/bash")
            task_id = pyjob.cluster.submit(job)
            logger.info(f"Launched task {task_id}")
        else:
            try:
                p = Processor(input_path,
                              oli_format=args.export_oli_as)
                target_bands = []
                if args.bands:
                    target_bands = list(map(lambda s:s.strip(),args.bands.split(",")))
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
                         max_lat=args.max_lat, max_lon=args.max_lon, inject_metadata=inject_metadata)
            except Exception as ex:
                logger.exception(f"Processing failed for {input_path}: "+str(ex))

if __name__ == '__main__':
    main()
