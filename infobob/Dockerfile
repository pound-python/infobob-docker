FROM pypy:2

WORKDIR /usr/src/app
COPY requirements.txt ./
COPY klein klein
RUN pip wheel --no-cache-dir -r requirements.txt -w wheelhouse

FROM pypy:2-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    runit libxml2 libxslt1.1 sqlite3 \
 && rm -rf /var/lib/apt/lists/*
RUN adduser --system --group --home /var/lib/infobob --disabled-login infobob

WORKDIR /usr/src/app
COPY --from=0 /usr/src/app/wheelhouse wheelhouse
COPY requirements.txt ./
COPY klein klein
RUN pip install --no-cache-dir --no-index -r requirements.txt -f wheelhouse

COPY . .
ENTRYPOINT ["./launch.sh"]
