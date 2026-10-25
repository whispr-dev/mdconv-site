"""Add one isolated Nginx virtual host, with webroot TLS and rollback."""
from __future__ import annotations
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from certbot_guard import run_certbot

DOMAIN = 'mdconv.site'
MARKER = '# MDCONV.SITE MANAGED NGINX CONFIGURATION'
WEBROOT = Path('/var/lib/mdconv-acme')
CERTDIR = Path('/etc/letsencrypt/live/mdconv.site')
AUXILIARY = (
    Path('/etc/systemd/system/mdconv-tls-renew.service'),
    Path('/etc/systemd/system/mdconv-tls-renew.timer'),
    Path('/var/lib/mdconv/tls-reload.sh'),
    Path('/var/lib/mdconv/certbot_guard.py'),
)


def command(*args):
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip() or 'command returned '+str(result.returncode)
        raise RuntimeError(' '.join(args)+': '+detail)
    return result


def atomic(path: Path, content: str, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.mdconv-tmp')
    temp.write_text(content)
    temp.chmod(mode)
    temp.replace(path)


def directives(config: str, directive: str):
    lexer = shlex.shlex(config, posix=True, punctuation_chars='{};')
    lexer.whitespace_split = True
    lexer.commenters = '#'
    tokens = iter(lexer)
    for token in tokens:
        if token == directive:
            values = []
            for item in tokens:
                if ';' in item or '{' in item or '}' in item:
                    break
                values.append(item)
            yield values


def nginx_config(ssl: bool, root=Path('/var/www/mdconv.site/current'),
                 webroot=WEBROOT, certdir=CERTDIR) -> str:
    text = MARKER + '\n' + f'''server {{
    listen 80;
    listen [::]:80;
    server_name {DOMAIN};
    access_log off;
    location ^~ /.well-known/acme-challenge/ {{
        root {webroot};
        default_type text/plain;
        try_files $uri =404;
    }}
    location / {{
'''
    text += f'        return 308 https://{DOMAIN}$request_uri;\n' if ssl else '        return 503;\n'
    text += '    }\n}\n'
    if ssl:
        text += f'''server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {DOMAIN};
    ssl_certificate {certdir}/fullchain.pem;
    ssl_certificate_key {certdir}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    access_log off;
    location ^~ /.well-known/acme-challenge/ {{
        root {webroot};
        default_type text/plain;
        try_files $uri =404;
    }}
    root {root};
    index index.html;
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    server_tokens off;
    autoindex off;
    add_header Content-Security-Policy "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; worker-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;
    add_header Cache-Control "no-cache" always;
    location / {{
        try_files $uri $uri/ =404;
    }}
    location ~ /\\. {{
        deny all;
    }}
}}
'''
    return text


class NginxFrontend:
    name = 'nginx'
    def __init__(self):
        self.path = None
        self.original = None
        self.backup = None

    def preflight(self):
        command('nginx','-t')
        dump = command('nginx','-T').stdout
        includes = [item[0] for item in directives(dump, 'include') if item]
        for pattern, target in (
            ('/etc/nginx/conf.d/*.conf', '/etc/nginx/conf.d/mdconv.conf'),
            ('conf.d/*.conf', '/etc/nginx/conf.d/mdconv.conf'),
            ('/etc/nginx/sites-enabled/*', '/etc/nginx/sites-enabled/mdconv.conf'),
            ('sites-enabled/*', '/etc/nginx/sites-enabled/mdconv.conf'),
        ):
            if pattern in includes:
                self.path = Path(target)
                break
        if self.path is None:
            raise RuntimeError('Nginx has no standard conf.d/*.conf or sites-enabled/* include. No configuration changed.')
        if self.path.is_symlink():
            raise RuntimeError(str(self.path)+' is a symlink; refusing to replace an existing site')
        if self.path.exists():
            self.original = self.path.read_text()
            if not self.original.startswith(MARKER+'\n'):
                raise RuntimeError(str(self.path)+' exists and is not managed by MDConv')
        # nginx -T labels each source file; reject an exact domain already owned elsewhere.
        for section in re.split(r'^# configuration file ', dump, flags=re.M):
            first, _, body = section.partition('\n')
            source = first.removesuffix(':').strip()
            if source == str(self.path):
                continue
            if any(DOMAIN in names for names in directives(body, 'server_name')):
                raise RuntimeError('An existing Nginx site already declares mdconv.site: '+source)
        print('Using the active Nginx service; site file: '+str(self.path), flush=True)

    def snapshot(self, directory: Path):
        self.backup = directory
        saved = []
        self.timer_enabled = subprocess.run(['systemctl','is-enabled','--quiet','mdconv-tls-renew.timer'],check=False).returncode == 0
        self.timer_active = subprocess.run(['systemctl','is-active','--quiet','mdconv-tls-renew.timer'],check=False).returncode == 0
        (directory/'timer-state.json').write_text(json.dumps({'enabled':self.timer_enabled,'active':self.timer_active}))
        for index, path in enumerate(AUXILIARY):
            exists = path.exists()
            if path.is_symlink():
                raise RuntimeError('Refusing to replace auxiliary symlink: '+str(path))
            if exists:
                shutil.copy2(path,directory/f'nginx-aux-{index}')
            saved.append({'path':str(path),'exists':exists})
        (directory/'nginx-aux.json').write_text(json.dumps(saved))

    def reload(self):
        command('nginx','-t')
        command('systemctl','reload','nginx')

    def activate(self):
        if not shutil.which('certbot'):
            subprocess.run(['apt-get','update'],check=True)
            subprocess.run(['apt-get','install','-y','certbot'],check=True)
        WEBROOT.mkdir(parents=True,exist_ok=True)
        WEBROOT.chmod(0o755)
        challenge = WEBROOT/'.well-known/acme-challenge'
        challenge.mkdir(parents=True,exist_ok=True)
        (WEBROOT/'.well-known').chmod(0o755)
        challenge.chmod(0o755)
        has_certificate = all((CERTDIR/name).is_file() for name in ('fullchain.pem','privkey.pem'))
        atomic(self.path,nginx_config(has_certificate))
        self.reload()
        print('Obtaining HTTPS certificate for mdconv.site through Nginx. DNS must point to lon1.',flush=True)
        result = run_certbot([
            'certbot','certonly','--webroot','--webroot-path',str(WEBROOT),
            '--cert-name',DOMAIN,'--domain',DOMAIN,'--keep-until-expiring',
            '--non-interactive','--agree-tos','--register-unsafely-without-email',
        ])
        if result.returncode:
            raise RuntimeError(f'Certbot failed to issue the HTTPS certificate (exit {result.returncode}). '
                               'Its output above contains the actual reason. This site will be rolled back.')
        atomic(self.path,nginx_config(True))
        self.reload()
        certbot = shutil.which('certbot')
        python = sys.executable
        guard = '/var/lib/mdconv/certbot_guard.py'
        nginx = shutil.which('nginx')
        systemctl = shutil.which('systemctl')
        # Paths come from the host's executable search and are quoted in the shell hook.
        hook = '#!/bin/sh\nset -eu\n'+shlex.quote(nginx)+' -t\n'+shlex.quote(systemctl)+' reload nginx\n'
        atomic(AUXILIARY[2],hook,0o755)
        for value in (certbot, python, guard, str(AUXILIARY[2])):
            if not re.fullmatch(r'/[A-Za-z0-9_./-]+',value):
                raise RuntimeError('Unsupported executable path for TLS renewal')
        service = f'''[Unit]
Description=Renew the MDConv HTTPS certificate
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
ExecStart={python} {guard} --wait-seconds 600 -- {certbot} renew --cert-name {DOMAIN} --quiet --deploy-hook {AUXILIARY[2]}
TimeoutStartSec=35min
'''
        timer = '''[Unit]
Description=Check MDConv HTTPS certificate twice daily
[Timer]
OnCalendar=*-*-* 03,15:15:00 UTC
RandomizedDelaySec=30min
Persistent=true
[Install]
WantedBy=timers.target
'''
        atomic(AUXILIARY[0],service)
        atomic(AUXILIARY[1],timer)
        command('systemctl','daemon-reload')
        command('systemctl','enable','--now','mdconv-tls-renew.timer')

    def restore(self):
        if self.original is None:
            self.path.unlink(missing_ok=True)
        else:
            atomic(self.path,self.original)
        if self.backup:
            saved = json.loads((self.backup/'nginx-aux.json').read_text())
            # Stop future scheduling, never interrupt an in-flight certificate job.
            subprocess.run(['systemctl','stop','mdconv-tls-renew.timer'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            timer_state = json.loads((self.backup/'timer-state.json').read_text())
            if not timer_state['enabled']:
                subprocess.run(['systemctl','disable','mdconv-tls-renew.timer'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for index,item in enumerate(saved):
                path = Path(item['path'])
                if item['exists']:
                    shutil.copy2(self.backup/f'nginx-aux-{index}',path)
                else:
                    path.unlink(missing_ok=True)
            command('systemctl','daemon-reload')
            if timer_state['enabled']:
                command('systemctl','enable','mdconv-tls-renew.timer')
            if timer_state['active']:
                command('systemctl','start','mdconv-tls-renew.timer')
        self.reload()
