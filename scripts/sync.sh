#!/bin/bash

# copy relevant files to a remove server

rootfolder=`dirname $0`/..

hostname=$1
username=$2
destfolder=$3

if [ -z ${hostname} ] || [ -z ${username} ] || [ -z ${destfolder} ];
then
  echo provide the hostname, username and destination folder as arguments
else
  rsync -avr $rootfolder/src $username@$hostname:$destfolder/landsat_importer
  rsync -avr $rootfolder/pyproject.toml $username@$hostname:$destfolder/landsat_importer
  rsync -avr $rootfolder/setup.cfg $username@$hostname:$destfolder/landsat_importer
fi


