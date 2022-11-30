#!/bin/bash
SCALELIB_VERSION=0.2.12
sudo apt-get install libncurses5-dev libncursesw5-dev

mkdir -p libs
mkdir -p modules/cyclecloud-scalelib
wget https://github.com/Azure/cyclecloud-scalelib/archive/refs/tags/$SCALELIB_VERSION.tar.gz -O modules/cyclecloud-scalelib-$SCALELIB_VERSION.tar.gz

tar -xvf modules/cyclecloud-scalelib-$SCALELIB_VERSION.tar.gz -C modules/cyclecloud-scalelib --strip-components 1

wget https://github.com/Azure/cyclecloud-slurm/releases/download/2.5.0/cyclecloud_api-8.1.0-py2.py3-none-any.whl -O libs/cyclecloud_api-8.1.0-py2.py3-none-any.whl

python3 -m venv ~/.virtualenvs/azhop-guac
. ~/.virtualenvs/azhop-guac/bin/activate
pip install -U pip
pip install wheel
pip install -r modules/cyclecloud-scalelib/dev-requirements.txt
pip install ./libs/cyclecloud_api-8.1.0-py2.py3-none-any.whl 
pip install mysql-connector-python==8.0.26

export AUTOSCALE_HOME=$(pwd)

#pip install ./packages/*
#pip install retry