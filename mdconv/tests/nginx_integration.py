#!/usr/bin/env python3
"""Exercise this site's generated configuration using an actual Nginx binary.

Usage: python3 tests/nginx_integration.py /absolute/path/to/nginx /absolute/path/to/mime.types
Needs OpenSSL and free loopback ports 8795/8796; never touches /etc or host services.
"""
import http.client
import importlib.util
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nginx_frontend import nginx_config

def run(binary,mime):
    with tempfile.TemporaryDirectory(prefix='mdconv-nginx-test-') as directory:
        base=Path(directory);(base/'logs').mkdir()
        # Nginx workers must be able to read this temporary test directory.
        base.chmod(0o755)
        cert=base/'cert';cert.mkdir()
        web=base/'web';(web/'.well-known/acme-challenge').mkdir(parents=True)
        (web/'.well-known/acme-challenge/probe').write_text('challenge works')
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=mdconv.site','-addext','subjectAltName=DNS:mdconv.site,IP:127.0.0.1','-keyout',str(cert/'privkey.pem'),'-out',str(cert/'fullchain.pem')],check=True,capture_output=True)
        config=nginx_config(True,root=ROOT/'site',webroot=web,certdir=cert)
        config=config.replace('listen 80;','listen 127.0.0.1:8795;').replace('    listen [::]:80;\n','').replace('listen 443 ssl;','listen 127.0.0.1:8796 ssl;').replace('    listen [::]:443 ssl;\n','').replace('/etc/nginx/mime.types',str(mime))
        config=('user root root;\n' if os.geteuid()==0 else '')+'daemon off;\nmaster_process off;\nevents {}\nhttp {\nserver { listen 127.0.0.1:8795; server_name ipanswers.space whatdoesmyscreen.fit lon.litehaus.online botforum.dev; return 200 "Other sites preserved"; }\n'+config+'\n}\n'
        path=base/'nginx.conf';path.write_text(config)
        checked=subprocess.run([str(binary),'-t','-p',str(base)+'/', '-c',str(path)],capture_output=True,text=True)
        assert checked.returncode==0,checked.stderr
        proxy=subprocess.Popen([str(binary),'-p',str(base)+'/', '-c',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        context=ssl.create_default_context(cafile=str(cert/'fullchain.pem'))
        def request(resource,https=True,host='mdconv.site'):
            connection=(http.client.HTTPSConnection('127.0.0.1',8796,context=context,timeout=2) if https else http.client.HTTPConnection('127.0.0.1',8795,timeout=2))
            connection.request('GET',resource,headers={'Host':host});response=connection.getresponse()
            status=response.status;headers=dict(response.getheaders());body=response.read();connection.close()
            return status,headers,body
        try:
            for attempt in range(30):
                try:status,headers,body=request('/');break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Test Nginx did not start')
            assert status==200 and b'Words in. Clarity out.' in body
            assert "connect-src 'none'" in headers['Content-Security-Policy']
            assert "worker-src 'self'" in headers['Content-Security-Policy']
            assert headers['X-Content-Type-Options']=='nosniff'
            for resource,mime_type in [('/worker.js','application/javascript'),('/vendor/marked.js','application/javascript'),('/vendor/purify.js','application/javascript'),('/vendor/diff/diff/line.js','application/javascript'),('/style.css','text/css'),('/assets/skeletrace-mark.svg','image/svg+xml')]:
                status,headers,body=request(resource)
                assert status==200,(resource,status);assert mime_type in headers['Content-Type'];assert body
            assert request('/deploy-server.py')[0]==404
            assert request('/.env')[0]==403
            for host in ('ipanswers.space','whatdoesmyscreen.fit','lon.litehaus.online','botforum.dev'):
                assert request('/',False,host)[2]==b'Other sites preserved'
            assert request('/.well-known/acme-challenge/probe',False)[2]==b'challenge works'
            assert request('/',False)[0]==308
            spec=importlib.util.spec_from_file_location('deployment',ROOT/'deploy-server.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.verify_https(port=8796,context=context)
            print('Real Nginx passed: HTTPS + hostname verification, worker/module MIME, CSP, assets, ACME, HTTP redirect, source isolation, and four neighboring host fixtures.')
        finally:
            proxy.terminate();proxy.wait(timeout=5)

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit(__doc__)
    run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
