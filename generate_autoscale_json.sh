#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

if [ $(whoami) != root ]; then
  echo "Please run as root"
  exit 1
fi

export PATH=$PATH:/root/bin

set -e

INSTALLDIR=/opt/cycle/guac
SPOOLDIR=/anfhome/guac_spool
USERNAME=
PASSWORD=
URL=
CLUSTER_NAME=

function usage() {
    echo Usage: $0 --username username --password password --url https://fqdn:port --cluster-name cluster_name --vaultname vault_name [--install-dir /opt/cycle/guac --spool-dir /anfhome/guac_spool]
    exit 2
}


while (( "$#" )); do
    case "$1" in
        --username)
            USERNAME=$2
            shift 2
            ;;
        --password)
            PASSWORD=$2
            shift 2
            ;;
        --url)
            URL=$2
            shift 2
            ;;
        --cluster-name)
            CLUSTER_NAME=$2
            shift 2
            ;;
        --install-dir)
            INSTALLDIR=$2
            shift 2
            ;;
        --spool-dir)
            SPOOLDIR=$2
            shift 2
            ;;
        --vaultname)
            VAULTNAME=$2
            shift 2
            ;;
        -*|--*=)
            echo "Unknown option $1" >&2
            usage
            ;;
        *)
            echo "Unknown option  $1" >&2
            usage
            ;;
    esac
done

if [ "$1" == "-h" ]; then usage; fi
if [ "$1" == "-help" ]; then usage; fi

if [ "$USERNAME" == "" ]; then usage; fi
if [ "$PASSWORD" == "" ]; then usage; fi
if [ "$URL" == "" ]; then usage; fi
if [ "$CLUSTER_NAME" == "" ]; then usage; fi
if [ "$INSTALLDIR" == "" ]; then usage; fi
if [ "$SPOOLDIR" == "" ]; then usage; fi

if [ -e $INSTALLDIR/autoscale.json ]; then
    if [ ! -e $INSTALLDIR/backups ]; then
        mkdir $INSTALLDIR/backups
    fi
    backup_file=$INSTALLDIR/backups/autoscale.json.$(date +%s)
    echo backing up $INSTALLDIR/autoscale.json to $backup_file
    cp $INSTALLDIR/autoscale.json $backup_file
fi

temp_autoscale=$TEMP/autoscale.json.$(date +%s)

                # --disable-default-resources \
                # --default-resource '{"select": {}, "name": "ncpus", "value": "node.pcpu_count"}' \
                # --default-resource '{"select": {}, "name": "ngpus", "value": "node.gpu_count"}' \
                # --default-resource '{"select": {}, "name": "disk", "value": "size::20g"}' \
                # --default-resource '{"select": {}, "name": "host", "value": "node.hostname"}' \
                # --default-resource '{"select": {}, "name": "slot_type", "value": "node.nodearray"}' \
                # --default-resource '{"select": {}, "name": "group_id", "value": "node.placement_group"}' \
                # --default-resource '{"select": {}, "name": "mem", "value": "node.memory"}' \
                # --default-resource '{"select": {}, "name": "vm_size", "value": "node.vm_size"}' \
                # --lock-file    $INSTALLDIR/scalelib.lock \
                # --log-config   $INSTALLDIR/logging.conf \
                # --guac-config /etc/guacamole/guacamole.properties \

(/usr/local/bin/azguac initconfig --cluster-name ${CLUSTER_NAME} \
                --username     ${USERNAME} \
                --password     ${PASSWORD} \
                --url          ${URL} \
                --idle-timeout 120 \
                --boot-timeout 1800 \
                --guac-vaultname $VAULTNAME \
                --guac-spool $SPOOLDIR \
                > $temp_autoscale && mv $temp_autoscale $INSTALLDIR/autoscale.json ) || (rm -f $temp_autoscale.json; exit 1)

echo testing that we can connect to CycleCloud...
chmod 600 $INSTALLDIR/autoscale.json
/usr/local/bin/azguac connect && echo success! || (echo Please check the arguments passed in and try again && exit 1)
