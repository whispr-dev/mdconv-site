import subprocess
import unittest
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nginx_frontend import NginxFrontend, MARKER, nginx_config

class NginxContracts(unittest.TestCase):
    def test_static_headers_and_isolation(self):
        config=nginx_config(True)
        for text in ('root /var/www/mdconv.site/current;',"connect-src 'none'","worker-src 'self'",'server_name mdconv.site;'):
            self.assertIn(text,config)
        for text in ('proxy_pass','default_server','ipanswers','screenfit','caddy'):
            self.assertNotIn(text,config)

    def test_acme_bootstrap_only(self):
        config=nginx_config(False)
        self.assertIn('location ^~ /.well-known/acme-challenge/',config)
        self.assertIn('return 503;',config)
        self.assertNotIn('listen 443',config)

    def test_conflicting_host_rejected(self):
        dump='# configuration file /etc/nginx/nginx.conf:\nhttp { include /etc/nginx/conf.d/*.conf; }\n# configuration file /etc/nginx/sites-enabled/old:\nserver { server_name mdconv.site; }\n'
        with patch('nginx_frontend.command',return_value=subprocess.CompletedProcess([],0,stdout=dump,stderr='')),patch.object(Path,'exists',return_value=False),patch.object(Path,'is_symlink',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'already declares'):
                NginxFrontend().preflight()

    def test_unmanaged_destination_rejected(self):
        dump='http { include /etc/nginx/conf.d/*.conf; }'
        with patch('nginx_frontend.command',return_value=subprocess.CompletedProcess([],0,stdout=dump,stderr='')),patch.object(Path,'exists',return_value=True),patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'read_text',return_value='unmanaged'):
            with self.assertRaisesRegex(RuntimeError,'not managed'):
                NginxFrontend().preflight()

    def test_managed_redeployment_allowed(self):
        config=nginx_config(True)
        dump='# configuration file /etc/nginx/nginx.conf:\nhttp { include /etc/nginx/conf.d/*.conf; }\n# configuration file /etc/nginx/conf.d/mdconv.conf:\n'+config
        with patch('nginx_frontend.command',return_value=subprocess.CompletedProcess([],0,stdout=dump,stderr='')),patch.object(Path,'exists',return_value=True),patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'read_text',return_value=config):
            front=NginxFrontend();front.preflight();self.assertEqual(front.path,Path('/etc/nginx/conf.d/mdconv.conf'))

    def test_rollback_preserves_other_sites_guard_and_timer_state(self):
        with TemporaryDirectory() as directory:
            base=Path(directory);site=base/'mdconv.conf';site.write_text(MARKER+'\nnew')
            other=base/'litehaus.conf';other.write_text('existing site')
            aux=tuple(base/name for name in ('renew.service','renew.timer','reload.sh','guard.py'))
            aux[0].write_text('previous service');aux[3].write_text('previous guard')
            backup=base/'backup';backup.mkdir()
            front=NginxFrontend();front.path=site;front.original=None
            with patch('nginx_frontend.AUXILIARY',aux),patch('nginx_frontend.subprocess.run',return_value=subprocess.CompletedProcess([],1)):
                front.snapshot(backup)
                for p in aux:p.write_text('changed')
                with patch('nginx_frontend.command') as run,patch('nginx_frontend.subprocess.run') as stop:
                    front.restore()
                    self.assertNotIn('mdconv-tls-renew.service',stop.call_args_list[0].args[0])
                    self.assertFalse(any('start' in call.args and 'mdconv-tls-renew.timer' in call.args for call in run.call_args_list))
            self.assertFalse(site.exists());self.assertEqual(other.read_text(),'existing site')
            self.assertEqual(aux[0].read_text(),'previous service');self.assertEqual(aux[3].read_text(),'previous guard')
            self.assertFalse(aux[1].exists());self.assertFalse(aux[2].exists())

if __name__=='__main__':unittest.main()
