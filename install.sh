#!/usr/bin/env bash

SCHEDULER=guac
INSTALL_PYTHON3=0
DISABLE_CRON=0
INSTALL_VIRTUALENV=0
VENV=/opt/cycle/${SCHEDULER}/venv


while (( "$#" )); do
    case "$1" in
        --install-python3)
            INSTALL_PYTHON3=1
            INSTALL_VIRTUALENV=1
            shift
            ;;
        --install-venv)
            INSTALL_VIRTUALENV=1
            shift
            ;;
        --disable-cron)
            DISABLE_CRON=1
            shift
            ;;
        --venv)
            VENV=$2
            shift 2
            ;;
        -*|--*=)
            echo "Unknown option $1" >&2
            exit 1
            ;;
        *)
            echo "Unknown option  $1" >&2
            exit 1
            ;;
    esac
done

echo INSTALL_PYTHON3=$INSTALL_PYTHON3
echo INSTALL_VIRTUALENV=$INSTALL_VIRTUALENV
echo VENV=$VENV

which python3 > /dev/null;
if [ $? != 0 ]; then
    if [ $INSTALL_PYTHON3 == 1 ]; then
        yum install -y python3 || exit 1
    else
        echo Please install python3 >&2;
        exit 1
    fi
fi

export PATH=$(python3 -c '
import os
paths = os.environ["PATH"].split(os.pathsep)
cc_home = os.getenv("CYCLECLOUD_HOME", "/opt/cycle/jetpack")
print(os.pathsep.join(
    [p for p in paths if cc_home not in p]))')

if [ $INSTALL_VIRTUALENV == 1 ]; then
    python3 -m pip install virtualenv
fi

python3 -m virtualenv --version 2>&1 > /dev/null
if [ $? != 0 ]; then
    if [ $INSTALL_VIRTUALENV ]; then
        python3 -m pip install virtualenv || exit 1
    else
        echo Please install virtualenv for python3 >&2
        exit 1
    fi
fi


python3 -m virtualenv $VENV
source $VENV/bin/activate

pip install -r requirements.txt
rm -f packages/zipp*.whl
pip install packages/*

echo "Copy logging configuration file"
cp ./conf/logging.conf /opt/cycle/${SCHEDULER}/logging.conf

cat > $VENV/bin/azguac <<EOF
#!$VENV/bin/python

from ${SCHEDULER}.cli import main
main()
EOF
chmod +x $VENV/bin/azguac

azguac -h 2>&1 > /dev/null || exit 1

ln -sf $VENV/bin/azguac /usr/local/bin/
echo "'azguac' installed. A symbolic link was made to /usr/local/bin/azguac"

# Remove any autoscale cron entries
crontab -l | grep -v '/usr/local/bin/azguac autoscale'  | crontab -

# Add autoscale cron entry if requested
if [ $DISABLE_CRON == 0 ]; then
    crontab -l | grep -q "/usr/local/bin/azguac autoscale"
    if [ $? != 0 ]; then
        echo "* * * * * /usr/local/bin/azguac autoscale -c /opt/cycle/${SCHEDULER}/autoscale.json" | crontab -
    fi
fi