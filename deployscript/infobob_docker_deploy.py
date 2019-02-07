import attr
import base64
import click
import docker
import hashlib
import os
import pathlib
import subprocess
import sys
import traceback

def _excepthook(typ, value, tb):
    if isinstance(value, subprocess.CalledProcessError):
        click.secho('\n{}'.format(value), fg='red')
    else:
        click.secho('\n*** traceback follows:', fg='red')
        error = ''.join(traceback.format_exception(typ, value, tb))
        click.secho(error, fg='red')

sys.excepthook = _excepthook

def echocmd(cmd):
    click.secho('==> {!r}'.format(cmd), fg='yellow')
    return cmd

checkout = pathlib.Path.cwd().joinpath('checkout')
config_dir = checkout.joinpath('infobob-config')
secrets = {
    'infobob-master-config': config_dir.joinpath('master.yaml'),
    'infobob-testing-config': config_dir.joinpath('testing.yaml'),
}

@attr.s
class Secret:
    name = attr.ib()
    hashed = attr.ib()
    sops_data = attr.ib()

    @property
    def full_name(self):
        return '{0.name}-{0.hashed}'.format(self)

    @property
    def env_name(self):
        return 'SECRET_HASH_{}'.format(self.name.replace('-', '_'))

def read_secrets():
    for name, path in secrets.items():
        sops_out = subprocess.run(
            echocmd(['sops', '-d', '--output-type', 'json', path]),
            stdout=subprocess.PIPE, check=True)
        with path.open('rb') as infile:
            data = infile.read()
        hashed = base64.b32encode(hashlib.blake2b(data, digest_size=10).digest()).decode().lower()
        yield Secret(name=name, hashed=hashed, sops_data=sops_out.stdout)

@click.group()
@click.option('--url', default='https://github.com/pound-python/infobob-docker')
@click.option('--branch', '-b', default='master')
def main(url, branch):
    # it'd be nice if you could set GNUPGHOME to a read-only directory, but
    # it does lockfiles and sockets and crap in there. also I don't trust
    # shutil to do this copy correctly.
    subprocess.check_call(echocmd([
        'cp', '-a', '/run/gnupg', '/tmp/gnupg',
    ]))
    subprocess.check_call(echocmd([
        'git', 'clone',
        '--depth=1', '--branch', branch,
        url, checkout,
    ]))

@main.command('hash')
def do_hash():
    for secret in read_secrets():
        click.echo('{0.name}: {0.hashed}'.format(secret))

@main.command('deploy')
def do_deploy():
    client = docker.from_env()
    loaded = list(read_secrets())

    for secret in loaded:
        try:
            client.secrets.get(secret.full_name)
        except docker.errors.NotFound:
            click.echo('creating secret: {}'.format(secret.full_name))
        else:
            click.echo('secret existed: {}'.format(secret.full_name))
            continue
        client.secrets.create(
            name=secret.full_name, data=secret.sops_data,
            labels={
                'org.pound-python.infobob.created-by': 'deploy.py',
                'org.pound-python.infobob.secret': secret.name,
            })

    env = dict(os.environ)
    for secret in loaded:
        env[secret.env_name] = secret.hashed

    # no 'docker stack' in docker-py
    subprocess.check_call(echocmd([
        'docker', 'stack', 'deploy',
        '--compose-file', checkout.joinpath('docker-stack.yml'),
        'infobob',
    ]), env=env)
