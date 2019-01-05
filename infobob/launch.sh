#!/bin/sh -eux
sqlite3 <db.schema /app/infobob.sqlite
exec twistd -n infobat infobob.cfg
