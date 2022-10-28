#!/bin/bash
# Delete a remote session by creating a delete command file in the spooler
THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ $# -le 2 ]; then
  echo "Usage delete_session.sh "
  echo "  Required arguments:"
  echo "    -s|--session <sesson_id> "
  echo "    -u|--user <user> "
  echo "   "

  exit 1
fi

while (( "$#" )); do
  case "${1}" in
    -s|--session)
      SESSION_ID=${2}
      shift 2
    ;;
    -u|--user)
      USER_SESSION=${2}
      shift 2
    ;;
  esac
done

if [ $(whoami) != root ]; then
  echo "Please run as root"
  exit 1
fi

SPOOLER_DIR=$(jq -r '.guac.spool_dir' $THIS_DIR/autoscale.json)

echo "Create delete spool request $SPOOLER_DIR/commands/$SESSION_ID.json"
cat <<EOF > $SPOOLER_DIR/commands/$SESSION_ID.json
{ "command": "delete" }
EOF

chown $USER_SESSION: $SPOOLER_DIR/commands/$SESSION_ID.json

ls -al $SPOOLER_DIR/commands

