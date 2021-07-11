import attr
import base64
import click
import docker
import hashlib
import json
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
hashed_files = {
    'infobob-master-config': {
        'path': config_dir.joinpath('master.yaml'),
        'sops_format': 'json',
    },
    'infobob-testing-config': {
        'path': config_dir.joinpath('testing.yaml'),
        'sops_format': 'json',
    },
    'webhooks-env': {
        'path': checkout.joinpath('webhooks-env.yaml'),
        'sops_format': 'dotenv',
    },
    'caddyfile-txt': {
        'path': checkout.joinpath('caddyfile-prod.txt'),
    },
}

@attr.s
class Hashed:
    name = attr.ib()
    hashed = attr.ib()
    sops_data = attr.ib()

    @property
    def full_name(self):
        return '{0.name}-{0.hashed}'.format(self)

    @property
    def env_name(self):
        return 'HASHED_{}'.format(self.name.replace('-', '_'))

    @classmethod
    def from_path(cls, name, path, *, sops_format=None):
        if sops_format is not None:
            sops_out = subprocess.run(
                echocmd(['sops', '-d', '--output-type', sops_format, path]),
                stdout=subprocess.PIPE, check=True)
            sops_data = sops_out.stdout
        else:
            sops_data = None
        with path.open('rb') as infile:
            data = infile.read()
        hashed = base64.b32encode(hashlib.blake2b(data, digest_size=10).digest()).decode().lower()
        return cls(name=name, hashed=hashed, sops_data=sops_data)

def read_files():
    for name, args in hashed_files.items():
        yield Hashed.from_path(name, **args)

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
@click.option('-f', '--format', 'fmt', type=click.Choice([
    'json', 'env', 'env-oneline',
], case_sensitive=False), default='json')
def do_hash(fmt):
    as_env = fmt in ('env', 'env-oneline')
    as_dict = {
        (f.env_name if as_env else f.name): f.hashed
        for f in read_files()}
    if fmt == 'json':
        click.echo(json.dumps(as_dict, indent=2))
    elif as_env:
        env_items = ['{}={}'.format(*kv) for kv in as_dict.items()]
        separator = ' ' if fmt == 'env-oneline' else '\n'
        click.echo(separator.join(env_items))

@main.command('deploy')
def do_deploy():
    client = docker.from_env()
    loaded = list(read_files())

    for secret in loaded:
        if secret.sops_data is None:
            continue
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
    for f in loaded:
        env[f.env_name] = f.hashed

    # no 'docker stack' in docker-py
    subprocess.check_call(echocmd([
        'docker', 'stack', 'deploy',
        '--compose-file', checkout.joinpath('docker-stack.yml'),
        'infobob',
    ]), env=env)
