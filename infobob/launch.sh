#!/bin/sh -eux
sqlite3 <db.schema /app/infobob.sqlite
chown infobob: /app/infobob.sqlite
exec chpst -u infobob twistd --pidfile= -n infobat infobob.cfg
