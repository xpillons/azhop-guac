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
rm -f packages/requests*.whl
rm -r packages/charset_normalizer*.whl
rm -f packages/typing_extensions*.whl

pip install packages/*

echo "Copy logging configuration file"
cp ./conf/logging.conf /opt/cycle/${SCHEDULER}/logging.conf

echo "Copy helper scripts"
cp ./delete_session.sh /opt/cycle/${SCHEDULER}/delete_session.sh

cat > $VENV/bin/azguac <<EOF
#!$VENV/bin/python

from ${SCHEDULER}.cli import main
main()
EOF
chmod +x $VENV/bin/azguac

azguac -h 2>&1 > /dev/null || exit 1

ln -sf $VENV/bin/azguac /usr/local/bin/
echo "'azguac' installed. A symbolic link was made to /usr/local/bin/azguac"

cat > $VENV/bin/azguac-spooler <<EOF
#!$VENV/bin/python

from ${SCHEDULER}.spooler import main
main()
EOF
chmod +x $VENV/bin/azguac-spooler
ln -sf $VENV/bin/azguac-spooler /usr/local/bin/
echo "'azguac-spooler' installed. A symbolic link was made to /usr/local/bin/azguac-spooler"

cat > $VENV/bin/azguac-daemon <<EOF
#!$VENV/bin/python

from ${SCHEDULER}.daemon import main
main()
EOF
chmod +x $VENV/bin/azguac-daemon
ln -sf $VENV/bin/azguac-daemon /usr/local/bin/
echo "'azguac-daemon' installed. A symbolic link was made to /usr/local/bin/azguac-daemon"

cat > /etc/systemd/system/guacspoold.service <<EOF
[Unit]
Description=The spooler for autoscaling guacamole instances
After=syslog.target network.target remote-fs.target nss-lookup.target
[Service]
Type=simple
PIDFile=/run/guacspoold.pid
ExecStart=/usr/local/bin/azguac-daemon -c /opt/cycle/${SCHEDULER}/autoscale.json
Restart=always
[Install]
WantedBy=multi-user.target
EOF

systemctl enable guacspoold.service
systemctl start guacspoold.service
