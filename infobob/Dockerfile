FROM pypy:2

WORKDIR /usr/src/app
COPY src/current-requirements.txt ./
RUN pip wheel --no-cache-dir -r current-requirements.txt -w wheelhouse

FROM pypy:2-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    jq runit libxml2 libxslt1.1 sqlite3 \
 && rm -rf /var/lib/apt/lists/*
RUN adduser --system --group --home /var/lib/infobob --disabled-login infobob

WORKDIR /usr/src/app
COPY --from=0 /usr/src/app/wheelhouse wheelhouse
RUN pip install ./wheelhouse/*

COPY src .
COPY config-template.json launch.sh ./
ENTRYPOINT ["./launch.sh"]
