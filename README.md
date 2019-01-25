Requirements: docker, git-crypt

Setup:

1. From repo root, clone the infobob source into the right dir:

    `git clone git@github.com:pound-python/infobob.git infobob/src`

2. Unlock the secrets file: `git-crypt unlock`

3. Connect to the host, and forward the docker socket:

    `ssh -L ./docker.sock:/var/run/docker.sock $INFOBOB_HOST`

4. Tell docker about the socket: `export DOCKER_HOST=unix://$(pwd)/docker.sock`

5. Use docker-compose to do all the things:
    `docker-compose build`
    `docker-compose up -d`

6. **Important** re-lock the secrets file: `git-crypt lock`
