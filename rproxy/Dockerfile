FROM pypy:2

WORKDIR /usr/src/app
RUN pip wheel --no-cache-dir -w wheelhouse rproxy

FROM pypy:2-slim

RUN adduser --system --group --home /usr/src/app --disabled-login rproxy
WORKDIR /usr/src/app
COPY --from=0 /usr/src/app/wheelhouse wheelhouse
RUN pip install ./wheelhouse/*

RUN mkdir -p /usr/src/app/certs
RUN chown -R rproxy /usr/src/app/certs
VOLUME /usr/src/app/certs
USER rproxy
ADD rproxy.ini ./
ENTRYPOINT ["twist", "--log-format=text", "rproxy"]
EXPOSE 8080 8443
