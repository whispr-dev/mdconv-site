# MDConv — mdconv.site

Version 1.0.0 · © 2026 whispr.dev

A static, browser-only Markdown previewer and text comparison utility for the existing Nginx server on `lon1` (138.68.142.181). The SkeleTrace Suite advertising panel uses the same whispr.dev and SkeleTrace logos as the other utility sites.

## Use it

- **.md:** edit Markdown and see a live preview. GFM headings, tables, task lists, strikethrough, links and fenced code work. Code is displayed, never executed. Images become descriptive text; raw HTML is sanitised and active content removed.
- **.txt:** paste or open an original and revised text. See aligned, numbered lines, additions/deletions and character highlights inside paired changed lines. Swap the inputs, copy either one, or download the comparison as a readable text report.
- Inputs survive mode changes. Clear and Load example have an undo button until the next edit.
- Open UTF-8 text files under 1 MB. Processing accepts up to 250,000 characters and 5,000 lines per input, with bounded worker execution. Oversized input stays in the editor, with an explicit error; it is never silently truncated.
- Copy Markdown source, rendered text, or sanitised HTML. Download Markdown or an inert, self-contained HTML document. Diff download is a human-readable report, not a patch format.
- Markdown panes can scroll together proportionally. Text comparisons share one scroll container so aligned rows remain aligned. On narrow screens Markdown panes stack; diff columns remain side by side.
- Tab inserts two spaces in an editor; Escape returns focus to the mode switch. Shift+Tab exits backwards. Controls work by keyboard.

**Drafts live in tab memory only. Reloading or closing the tab loses them. Download work you want to keep.** A browser may show a leave-page warning after editing. There is no local storage, session storage, app cookie, tracking pixel, external font, runtime CDN dependency, analytics or text upload. The hosting/proxy still processes ordinary connection data. Preview links navigate only when clicked. Cloudflare security features may set their own cookies if you enable them.

## Before deployment: DNS

1. Confirm the registered domain is exactly **mdconv.site**.
2. In its authoritative DNS provider, add an **A** record: name **@**, value **138.68.142.181**. At Cloudflare use **DNS only** (grey cloud) for first certificate issuance.
3. Remove an obsolete AAAA record unless IPv6 actually reaches this same server. Only add `www` if you later configure it deliberately: this package serves the apex domain only.
4. If using Cloudflare DNS, the registrar must delegate to this zone's currently assigned Cloudflare nameservers. Merely adding records at another DNS provider does not change delegation.
5. Wait for resolution. From PowerShell:

```powershell
Resolve-DnsName mdconv.site -Type A -Server 1.1.1.1
```

Expect `138.68.142.181` while DNS-only. Inbound port 80 must reach Nginx for HTTP-01 validation; port 443 must reach it for the site. The installer checks that the domain resolves before changing site configuration. Successful DNS resolution alone does not prove it points to the right server; Certbot performs the public validation.

## Deploy from Windows

Requires PowerShell 7+, the Windows OpenSSH client (`ssh` and `scp`), Windows `tar`, and the existing `lon1` alias. No local Node, npm or Python installation is needed for deployment.

Save `mdconv-site-1.0.0.tar.gz` in Downloads, then run:

```powershell
Set-Location "$env:USERPROFILE\Downloads"
tar -xzf .\mdconv-site-1.0.0.tar.gz
Set-Location .\mdconv
.\Deploy.ps1
```

Enter the server sudo password if prompted. The script uploads only the complete static site and installer files, invokes the Python installer with sudo, and cleans up its uniquely named temporary directory after success. A failed installation leaves the uploaded installer for diagnosis and prints its path. It does not need your passwords in chat.

The installer assumes Ubuntu 22.04+ with Python 3.10+, systemd and an already active Nginx service. It installs distribution Certbot if absent. It never starts Caddy or creates an application listener, Node process or database. Existing unrelated Nginx hosts remain in place. Unknown/conflicting configuration for mdconv.site is rejected instead of overwritten.

After successful deployment open **https://mdconv.site/**. No extra application service is required. If restoring the Cloudflare proxy afterward, use **Full (strict)** TLS; leave HTTP-01 challenge delivery functional for renewals.

## Linux deployment alternative

From the extracted `mdconv` directory, using your existing SSH alias:

```bash
stage=$(mktemp -d)
tar -czf "$stage/site.tar.gz" site deploy-server.py nginx_frontend.py certbot_guard.py
remote=$(ssh lon1 'umask 077; mktemp -d /tmp/mdconv-XXXXXXXX')
scp "$stage/site.tar.gz" "lon1:$remote/site.tar.gz"
ssh -t lon1 "tar -xzf '$remote/site.tar.gz' -C '$remote' && sudo python3 '$remote/deploy-server.py'"
```

The remote directory is retained for diagnosis by this manual route. The PowerShell script is the recommended installer for this user's setup.

## Server paths and recovery

| Purpose | Path |
| --- | --- |
| Static releases | `/var/www/mdconv.site/releases/<timestamp>` |
| Active release symlink | `/var/www/mdconv.site/current` |
| Nginx host | `/etc/nginx/conf.d/mdconv.conf` (or the active standard `sites-enabled` include) |
| ACME webroot | `/var/lib/mdconv-acme` |
| Certificate | `/etc/letsencrypt/live/mdconv.site` |
| Isolated renewal timer | `mdconv-tls-renew.timer` |
| Root-owned renewal helper/hook | `/var/lib/mdconv/certbot_guard.py`, `/var/lib/mdconv/tls-reload.sh` |
| Configuration/release-state backups | `/var/backups/mdconv/<timestamp>` |
| Per-site installer lock | `/run/lock/mdconv-deploy.lock` |

The installer snapshots its own host/renewal files and timer state. It switches the release symlink, validates Nginx, obtains HTTPS through a temporary ACME-only HTTP host, then enables the HTTPS site and renewal timer. It verifies the local ACME route and the HTTPS page/worker/module using real certificate and hostname validation with `mdconv.site` as TLS SNI, without depending on Cloudflare routing. Any failure in that activation stage restores its previous release link, managed host and renewal files/state. Backups and failed release directories remain for diagnosis; certificates already issued and installed distribution packages are retained. It does not delete other certificates, modify neighboring host files, or change global Nginx/Caddy configuration.

Certbot contention waits up to ten minutes, retrying only its explicit “another instance … already running” error. Actual validation errors are printed and returned immediately. No certificate lock files are deleted, and no running certificate job is stopped. A timer checks this site's certificate twice daily with a random delay and reloads Nginx after a successful renewal. Keep working DNS and port-80 challenge access.

Useful read-only diagnostics from PowerShell:

```powershell
ssh -t lon1 'sudo nginx -t'
ssh -t lon1 'sudo systemctl status mdconv-tls-renew.timer --no-pager'
ssh -t lon1 'sudo journalctl -u mdconv-tls-renew.service -n 60 --no-pager'
```

Re-running `Deploy.ps1` updates this managed host with a new release and backup. Never delete Certbot locks or stop Nginx to resolve a busy certificate job.

## Local preview and tests

Production needs no build step or npm install. All required browser libraries are vendored in `site/vendor/` with exact versions, upstream licenses and registry integrity metadata. Serve `site/` over HTTP for local development; module workers do not work reliably from `file://`.

With Python 3.10+ on Windows:

```powershell
Set-Location "$env:USERPROFILE\Downloads\mdconv"
python -m http.server 4173 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:4173/`. Press Ctrl+C to stop. This command is for a local development preview only; public deployment uses the hardened Nginx configuration.

With Node 22+ and Python 3.10+ for tests:

```powershell
node --test tests/core.test.mjs
python -m unittest discover -s tests -v
```

On Linux, an additional real-Nginx integration check requires OpenSSL, an Nginx executable built with TLS support, a MIME file, and free loopback ports 8795/8796:

```bash
python3 tests/nginx_integration.py /usr/sbin/nginx /etc/nginx/mime.types
```

It uses a temporary prefix and a locally trusted test certificate. It does not touch `/etc`, reload a system service or request a public certificate.

Validation for this release: 19 JavaScript tests (including 250 deterministic random reconstruction cases), 13 Python tests, real Nginx HTTPS/module/ACME/neighbor-host checks, and browser checks for both modes, sanitisation, clipboard feedback, clear/undo and a 390-pixel mobile frame. Public deployment and Let's Encrypt issuance on lon1 must be performed by the owner using the supplied SSH script; they cannot be verified from this workspace.

## Diff details and limits

Diff is case- and whitespace-sensitive. CRLF and CR are normalised to LF. A missing final newline remains a difference and is displayed as `↵ No final newline`. Deleted/added runs are paired in order for presentation; there is no moved-block detector. Inline character highlighting falls back to whole-line colour for long or expensive pairs. Very dissimilar inputs may exceed the comparison budget even within the size limit; the UI asks for a smaller selection instead of presenting a fabricated result. Each worker has a hard time limit and is terminated when its result is superseded.

## Dependencies and references

Pinned browser assets (SHA-512 integrity checked against npm registry metadata when packaged):

- Marked **18.1.1** — <https://github.com/markedjs/marked>, MIT. Markdown parser; its HTML output is always sanitised.
- DOMPurify **3.4.17** — <https://github.com/cure53/DOMPurify>, Apache-2.0 OR MPL-2.0. Restricted allowlist; removes active content, styling, IDs and names; links get safe navigation attributes; only disabled task checkboxes are retained.
- jsdiff **9.0.0** — <https://github.com/kpdecker/jsdiff>, BSD-3-Clause. Bounded line and character comparison.

Exact integrity values are included in `site/vendor/versions.json`. No vendor package install runs on the production server. Dependencies still need periodic security updates; a static site is not an excuse to freeze parsers forever.

Primary implementation references:

- <https://marked.js.org/using_advanced> — GFM options, worker processing and sanitisation guidance.
- <https://github.com/cure53/DOMPurify#readme> — sanitiser allowlists and DOM fragments.
- <https://github.com/kpdecker/jsdiff#readme> — diffLines/diffChars, timeout/maxEditLength and EOF behavior.
- <https://nginx.org/en/docs/http/ngx_http_core_module.html> — static hosts, roots and locations.
- <https://eff-certbot.readthedocs.io/en/stable/using.html> — webroot certificates, renewal and locking.

The logos are the existing whispr.dev/SkeleTrace brand assets supplied for these utility sites. The graph is an illustration, not live investigation data.
