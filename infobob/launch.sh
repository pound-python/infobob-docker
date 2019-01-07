#!/bin/sh -eu
jq --arg znc_password "${ZNC_PASSWORD}" \
    '.irc.password = $znc_password' \
    config-template.json >config.json
set -x
sqlite3 <db.schema /app/infobob.sqlite
chown infobob: /app/infobob.sqlite
exec chpst -u infobob twistd --pidfile= -n infobat config.json
