#!/usr/bin/env python3
"""Install the static Markdown and text diff utility (mdconv.site) on LON1.

LON1 is served by Caddy since 30 Oct 2026; the Caddyfile belongs to the lon1-caddy-kit and is
never edited here. With Caddy running, this checks Caddy already serves mdconv.site from
/var/www/mdconv.site/current, swaps in the new release, and proves Caddy serves it byte-for-byte.
If nginx is the running server instead (the kit's 4-rollback.sh), the original nginx route runs.
"""
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
from caddy_site import require_route, verify_static, web_server

SOURCE = Path(__file__).resolve().parent
BASE = Path('/var/www/mdconv.site')
STATE = Path('/var/lib/mdconv')
HOST = 'mdconv.site'
SITE_FILES = ('index.html','style.css','promotion.css','app.js','core.js','render.js','worker.js','vendor/marked.js','vendor/purify.js','vendor/diff/diff/line.js','vendor/diff/diff/character.js','assets/whispr-logo.svg','assets/skeletrace-mark.svg')


def verify_https(port=443, context=None):
    """Check the loopback vhost with real hostname and certificate validation."""
    context = context or ssl.create_default_context()
    for resource, expected in (('/',b'Words in. Clarity out.'),('/worker.js',b'compareTexts'),('/vendor/diff/diff/line.js',b'diffLines')):
        raw = socket.create_connection(('127.0.0.1',port),timeout=10)
        try:
            secure = context.wrap_socket(raw,server_hostname=HOST)
        except Exception:
            raw.close()
            raise
        connection = http.client.HTTPConnection(HOST,timeout=10)
        connection.sock = secure
        try:
            connection.request('GET',resource,headers={'Host':HOST})
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
    if not shutil.which('systemctl'):
        raise RuntimeError('Required command missing: systemctl')
    server = web_server()
    # Stop before changing anything when the domain has no DNS yet.
    try:
        socket.getaddrinfo(HOST,80,type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise RuntimeError(HOST+' does not resolve on this host yet. Set its A record to 138.68.142.181, wait for DNS, then rerun. No site configuration changed.') from error
    frontend = None
    if server == 'nginx':
        from nginx_frontend import NginxFrontend
        frontend = NginxFrontend()
        frontend.preflight()
    else:
        require_route(HOST, root=BASE/'current')
    for name in SITE_FILES:
        if not (SOURCE/'site'/name).is_file():
            raise RuntimeError('Site package is missing '+name)
    if (BASE/'current').exists() and not (BASE/'current').is_symlink():
        raise RuntimeError(str(BASE/'current')+' is not a managed release link')
    previous = os.readlink(BASE/'current') if (BASE/'current').is_symlink() else None
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = Path('/var/backups/mdconv')/stamp
    backup.mkdir(parents=True)
    if frontend:
        frontend.snapshot(backup)
        if frontend.path.exists():
            shutil.copy2(frontend.path,backup/'nginx-site.conf')
    (backup/'state.json').write_text(json.dumps({'previous_release':previous,'web_server':server,
                                                 'nginx_site':str(frontend.path) if frontend else None}))
    release = BASE/'releases'/stamp
    release.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(SOURCE/'site',release)
    for path in [BASE,BASE/'releases',release,*release.rglob('*')]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    changed = False
    try:
        changed = True
        link = BASE/'current-next'
        link.unlink(missing_ok=True)
        link.symlink_to(release)
        os.replace(link,BASE/'current')
        if frontend:
            STATE.mkdir(parents=True,exist_ok=True)
            STATE.chmod(0o755)
            from nginx_frontend import atomic
            atomic(STATE/'certbot_guard.py',(SOURCE/'certbot_guard.py').read_text())
            frontend.activate()
            # Check local routing with the correct Host, without relying on external DNS.
            request = urllib.request.Request('http://127.0.0.1/.well-known/acme-challenge/mdconv-health',headers={'Host':HOST})
            challenge = Path('/var/lib/mdconv-acme/.well-known/acme-challenge/mdconv-health')
            challenge.write_text('mdconv-ready')
            try:
                with urllib.request.urlopen(request,timeout=10) as response:
                    if response.read() != b'mdconv-ready':
                        raise RuntimeError('Nginx host routing check failed')
            finally:
                challenge.unlink(missing_ok=True)
        else:
            verify_static(HOST, release, ['index.html','app.js','worker.js','vendor/diff/diff/line.js'])
        verify_https()
        print('\nInstalled successfully: https://'+HOST+'  (served by '+server+')')
        print('Backup: '+str(backup))
        print('Static site: no app process, database or additional listening port.')
    except Exception:
        if changed:
            if previous:
                (BASE/'current').unlink(missing_ok=True)
                (BASE/'current').symlink_to(previous)
            else:
                (BASE/'current').unlink(missing_ok=True)
            print('Put the previous release back.',file=sys.stderr)
            if frontend:
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
