#!/bin/sh -eu
jq --arg znc_password "${ZNC_PASSWORD}" \
    '.irc.password = $znc_password' \
    config-template.json >config.json
set -x
mkdir -p /app/db
sqlite3 <db.schema /app/db/infobob.sqlite
chmod -R go= /app/db
chown -R infobob: /app/db
exec chpst -u infobob twistd --pidfile= -n infobat config.json
