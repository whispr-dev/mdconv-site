#!/usr/bin/env python3
"""Install a static Markdown and text diff utility alongside the existing London Nginx sites."""
from __future__ import annotations
import datetime as dt
import fcntl
import http.client
import socket
import ssl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
from nginx_frontend import NginxFrontend

SOURCE = Path(__file__).resolve().parent
BASE = Path('/var/www/mdconv.site')
STATE = Path('/var/lib/mdconv')


def verify_https(port=443, context=None):
    """Check the loopback vhost with real hostname and certificate validation."""
    context = context or ssl.create_default_context()
    for resource, expected in (('/',b'Words in. Clarity out.'),('/worker.js',b'compareTexts'),('/vendor/diff/diff/line.js',b'diffLines')):
        raw = socket.create_connection(('127.0.0.1',port),timeout=10)
        try:
            secure = context.wrap_socket(raw,server_hostname='mdconv.site')
        except Exception:
            raw.close()
            raise
        connection = http.client.HTTPConnection('mdconv.site',timeout=10)
        connection.sock = secure
        try:
            connection.request('GET',resource,headers={'Host':'mdconv.site'})
            response = connection.getresponse()
            body = response.read(1_000_000)
            if response.status != 200 or expected not in body:
                raise RuntimeError('HTTPS site verification failed for '+resource)
        finally:
            connection.close()


def main():
    os.umask(0o022)
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo python3 deploy-server.py')
    for name in ('nginx','systemctl','python3'):
        if not shutil.which(name):
            raise RuntimeError('Required command missing: '+name)
    subprocess.run(['systemctl','is-active','--quiet','nginx'],check=True)
    # Stop before changing web configuration when the domain has no DNS yet.
    try:
        socket.getaddrinfo('mdconv.site',80,type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise RuntimeError('mdconv.site does not resolve on this host yet. Set its A record to 138.68.142.181, wait for DNS, then rerun. No site configuration changed.') from error
    frontend = NginxFrontend()
    frontend.preflight()
    for name in ('index.html','style.css','promotion.css','app.js','core.js','render.js','worker.js','vendor/marked.js','vendor/purify.js','vendor/diff/diff/line.js','vendor/diff/diff/character.js','assets/whispr-logo.svg','assets/skeletrace-mark.svg'):
        if not (SOURCE/'site'/name).is_file():
            raise RuntimeError('Site package is missing '+name)
    if (BASE/'current').exists() and not (BASE/'current').is_symlink():
        raise RuntimeError(str(BASE/'current')+' is not a managed release link')
    previous = os.readlink(BASE/'current') if (BASE/'current').is_symlink() else None
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = Path('/var/backups/mdconv')/stamp
    backup.mkdir(parents=True)
    frontend.snapshot(backup)
    if frontend.path.exists():
        shutil.copy2(frontend.path,backup/'nginx-site.conf')
    (backup/'state.json').write_text(json.dumps({'previous_release':previous,'nginx_site':str(frontend.path)}))
    release = BASE/'releases'/stamp
    release.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(SOURCE/'site',release)
    for path in [BASE,BASE/'releases',release,*release.rglob('*')]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    STATE.mkdir(parents=True,exist_ok=True)
    STATE.chmod(0o755)
    changed = False
    try:
        changed = True
        link = BASE/'current-next'
        link.unlink(missing_ok=True)
        link.symlink_to(release)
        os.replace(link,BASE/'current')
        from nginx_frontend import atomic
        atomic(STATE/'certbot_guard.py',(SOURCE/'certbot_guard.py').read_text())
        frontend.activate()
        # Check local routing with the correct Host, without relying on external DNS.
        request = urllib.request.Request('http://127.0.0.1/.well-known/acme-challenge/mdconv-health',headers={'Host':'mdconv.site'})
        challenge = Path('/var/lib/mdconv-acme/.well-known/acme-challenge/mdconv-health')
        challenge.write_text('mdconv-ready')
        try:
            with urllib.request.urlopen(request,timeout=10) as response:
                if response.read() != b'mdconv-ready':
                    raise RuntimeError('Nginx host routing check failed')
        finally:
            challenge.unlink(missing_ok=True)
        verify_https()
        print('\nInstalled successfully: https://mdconv.site')
        print('Backup: '+str(backup))
        print('Static site: no app process, database or additional listening port.')
    except Exception:
        if changed:
            if previous:
                (BASE/'current').unlink(missing_ok=True)
                (BASE/'current').symlink_to(previous)
            else:
                (BASE/'current').unlink(missing_ok=True)
            try:
                frontend.restore()
            except Exception as error:
                print('Rollback needs attention: '+str(error)+'; backup: '+str(backup),file=sys.stderr)
        raise

if __name__=='__main__':
    try:
        # Serialize deployments of this site only; other sites and renewals continue.
        with open('/run/lock/mdconv-deploy.lock','w') as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another MDConv deployment is running. Let it finish, then retry.')
            main()
    except Exception as error:
        print('ERROR: '+str(error),file=sys.stderr)
        sys.exit(1)
