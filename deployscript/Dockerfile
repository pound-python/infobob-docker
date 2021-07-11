FROM python:3.7-slim
WORKDIR /usr/src/app
ADD https://github.com/mozilla/sops/releases/download/3.2.0/sops-3.2.0.linux /usr/local/bin/sops
RUN chmod +x /usr/local/bin/sops
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y docker.io git gnupg
ENV GNUPGHOME=/tmp/gnupg
RUN pip install -U pip setuptools poetry
ADD . .
RUN pip install --no-cache-dir .
ENTRYPOINT ["infobob-docker-deploy"]
