# FortiWarn — Setup Guide

FortiWarn monitors a Fortinet HA pair for SDWAN connection switches. It detects when the internet connection transitions from a primary interface to a backup interface and sends an email alert.

## Quick Start

```bash
git clone <repo-url> && cd fortiwarn
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # or: pip install python-dotenv jinja2 httpx pydantic pydantic-settings pytest pytest-asyncio pytest-cov
cp .env.example .env
# Edit .env (see below)
python fortivarn/controllers/daemon_controller.py
```

## 1. FortiGate Configuration

Perform these steps on **both HA peers** so the daemon can query either unit without disruption during failover.

### 1.1 Interface Names

Identify your SDWAN WAN members on the FortiGate:

```bash
get system sdwan
```

From the output, note the interface names listed under `members:`. For a FortiGate 101F, you might see something like:

```
members:
    == [ 2 ]
    seq-num:     2       interface: x2            zone: virtual-wan-link        
    == [ 3 ]
    seq-num:     3       interface: x1            zone: virtual-wan-link        
```

Use the `interface:` values (`x2`, `x1` in this example) in your `.env`:
- **MAIN_INTERFACE** = the first (higher-seq-num or primary) member, e.g., `x2`
- **BACKUP_INTERFACE** = the second member, e.g., `x1`

> Note: On newer FortiOS versions with vlink interfaces, the interface name may differ. Always confirm from the actual output above.

### 1.2 API Token Authentication (Recommended)

Generate a long-lived access token for an admin user via CLI or GUI:

```bash
execute api-user generate-key <username> [expiry-in-minutes]
```

The FortiGate prints the one-time key, e.g.: `fccys3cfbhyhqbqghkyzm1QGNnm31r`

This token is passed as ``Authorization: Bearer <token>`` in every API request. No login step or session refresh is needed — tokens are valid until revoked or expired on the device side.

### 1.3 Username / Password Authentication (Fallback)

If not using an API token, set `FORTINET_USERNAME` and `FORTINET_PASSWORD`. The daemon obtains a short-lived session key via ``POST /api/v2/authentication`` and automatically re-authenticates when it expires (default TTL ~25 minutes).

### 1.4 VDOM Considerations

Add `FORTINET_VDOM` to your `.env` if the FortiGate runs in multi-VDOM mode:

```ini
FORTINET_VDOM=root   # or another named vdom
```

The daemon passes ``?vdom=<name>`` on every API call. Without this, calls may fail with 403 or return data from an unexpected VDOM in HA/multi-VDOM setups.

### 1.5 Firewall Rules

Ensure your server running FortiWarn can reach the FortiGate:

```bash
curl -k https://<FORTINET_HOST>/api/v2/monitor/virtual-wan/health-check \
      -H 'Authorization: Bearer <API_TOKEN>' \
      2>&1 | python -m json.tool
```

The response should contain a JSON object with per-interface health data. If not, check that:
- The FortiGate allows HTTPS API access from your server's IP.
- The admin profile permits CLI/API access.

## 2. .env Reference

Create or edit `.env` at the project root:

| Variable | Required | Example | Notes |
|---|---|---|---|
| `FORTINET_HOST` | Yes | `192.168.10.1` | IP or hostname of the FortiGate HA pair |
| `FORTINET_USERNAME` | Conditionally | `admin` | Required if not using API key auth |
| `FORTINET_PASSWORD` | Conditionally | `"mysecurepassword"` | Required if not using API key auth |
| `FORTINET_API_KEY` | Conditionally | `"aBcD-eFgH-..."` | Recommended over username/password |
| `MAIN_INTERFACE` | Yes | `x2` | Primary SDWAN WAN member name (from `get system sdwan`) |
| `BACKUP_INTERFACE` | Yes | `x1` | Backup SDWAN WAN member name (from `get system sdwan`) |
| `SMTP_SERVER` | Yes | `smtp.gmail.com` | SMTP hostname |
| `SMTP_PORT` | Yes | `587` | Port (587 for STARTTLS, 465 for SSL) |
| `SMTP_USER` | Yes | `alerts@example.com` | SMTP sender username |
| `SMTP_PASSWORD` | Yes | `app-password` | SMTP password |
| `EMAIL_FROM` | Yes | `fortivarn@example.com` | Sender address |
| `EMAIL_TO` | Yes | `ops@example.com` | Alert recipient |
| `CHECK_INTERVAL_SECONDS` | No | `60` | Default 60 seconds between checks |

## 3. How It Works

1. If using an **API token**, the daemon verifies it once at startup and then includes ``Authorization: Bearer <token>`` on every request (no session to refresh).
2. If using **username/password**, the daemon calls ``POST /api/v2/authentication`` with credentials and obtains a short-lived session key, which is automatically re-obtained when expired (~25 min TTL).
3. Every interval it queries:

   ```
   GET /api/v2/monitor/virtual-wan/health-check?vdom=root
   ```

   This single call returns the health status of all SD-WAN member interfaces (latency, jitter, packet_loss) in one round-trip — no redundant API calls.

4. A switch is confirmed only when **both** conditions hold: main interface reports ``down`` AND backup explicitly exists and reports ``up``. This avoids false positives during transient failures where both links may briefly flap simultaneously.
5. When the connection returns to normal, internal state resets — no redundant email is sent.

## 4. Running as a Background Service

```bash
nohup python fortivarn/controllers/daemon_controller.py > /var/log/fortivarn.log 2>&1 &
# Or use systemd:
sudo tee /etc/systemd/system/fortivarn.service <<EOF
[Unit]
Description=FortiWarn SDWAN Monitor Daemon
After=network-online.target

[Service]
ExecStart=/home/<user>/fortiwarn/venv/bin/python fortivarn/controllers/daemon_controller.py
WorkingDirectory=/home/<user>/fortiwarn
EnvironmentFile=/home/<user>/fortiwarn/.env
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now fortivarn
```

## 5. Email Warning System

FortiWarn sends **two distinct email alerts**, each fired exactly once per state transition (rising edge). State is tracked in memory so you do not receive a fresh email on every polling interval while a problem persists.

| Alert | Subject | Trigger condition | Template |
|---|---|---|---|
| **Failover** | `ALERT: SDWAN Connection Switched to Backup` | Main interface DOWN **and** backup UP | `switch_alert.html` |
| **Redundancy lost** | `WARNING: SDWAN Backup Link Down — Redundancy Lost` | Main UP **and** backup DOWN | `backup_down_alert.html` |

Both emails reset their internal "already sent" flag the moment the condition clears, so a flapping link will produce one email per real transition — not a stream.

Why two alerts? When the backup is dead but the main is still serving traffic, users see no impact, but you have silently lost your failover capability. Catching that early prevents a small problem (one ISP down) from becoming a hard outage (both ISPs down with no redundancy left).

### 5.1 Choose an SMTP relay

Any RFC-compliant SMTP server works. Pick the row that matches your environment:

| Provider | `SMTP_SERVER` | `SMTP_PORT` | Auth notes |
|---|---|---|---|
| Gmail / Google Workspace | `smtp.gmail.com` | `587` | Requires an **App Password** (account → Security → 2-Step Verification → App passwords). Regular password will not work. |
| Microsoft 365 | `smtp.office365.com` | `587` | Requires SMTP AUTH enabled on the mailbox + an App Password if MFA is on. |
| Amazon SES | `email-smtp.<region>.amazonaws.com` | `587` | Use the SMTP credentials generated in the SES console (not your AWS IAM key). |
| SendGrid | `smtp.sendgrid.net` | `587` | `SMTP_USER=apikey`, `SMTP_PASSWORD=<your API key>`. |
| Internal Postfix relay | `mail.corp.local` | `25` or `587` | Auth optional — see § 5.4 for unauthenticated relays. |

Port semantics used by FortiWarn:

- **587** → STARTTLS is performed automatically.
- **465** → STARTTLS is performed automatically. (Note: 465 is technically implicit-TLS; the current implementation uses STARTTLS for both 587 and 465. Use 587 if your provider supports it.)
- **Any other port** → plain SMTP, no encryption upgrade. Only use this on a trusted internal relay.

### 5.2 Configure `.env`

Add the SMTP block to your `.env`:

```ini
# --- Email alerting ---
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD="abcd efgh ijkl mnop"   # quote app passwords that contain spaces
EMAIL_FROM=fortiwarn@example.com      # must match SMTP_USER for most providers
EMAIL_TO=ops@example.com              # single recipient
```

Notes:
- `EMAIL_FROM` must match (or be authorised by) `SMTP_USER`. Gmail/M365 will silently rewrite or reject mismatched From addresses.
- `EMAIL_TO` currently accepts a single address. To fan out, point it at a distribution list on your mail server.
- Restart the daemon after editing `.env` — settings are loaded once at startup.

### 5.3 Test the email path end-to-end

The cleanest way to verify SMTP without waiting for a real failover is to call the email service directly from a Python REPL. Run **both** snippets so you confirm both alert paths work:

```bash
cd /home/<user>/fortiwarn
source venv/bin/activate
export PYTHONPATH=.

# 1. Test the failover alert
python - <<'PY'
import asyncio
from fortivarn.config.settings import FortiWarnSettings
from fortivarn.views.email_service import EmailService

async def main():
    s = FortiWarnSettings()
    await EmailService(s).send_switch_alert(s.main_interface, s.backup_interface)
    print("Failover alert sent.")

asyncio.run(main())
PY

# 2. Test the "backup down — redundancy lost" alert
python - <<'PY'
import asyncio
from fortivarn.config.settings import FortiWarnSettings
from fortivarn.views.email_service import EmailService

async def main():
    s = FortiWarnSettings()
    await EmailService(s).send_backup_down_alert(s.main_interface, s.backup_interface)
    print("Redundancy-lost alert sent.")

asyncio.run(main())
PY
```

You should receive both emails within a few seconds. If not, check:

| Symptom | Likely cause |
|---|---|
| `SMTPAuthenticationError` | Wrong password, or app password not generated, or 2FA blocking basic auth. |
| `SMTPSenderRefused` | `EMAIL_FROM` does not match the authenticated mailbox. |
| `SMTPServerDisconnected` | Wrong port (e.g. 465 used as plain SMTP) or firewall blocking egress 587/465/25. |
| `SMTPRecipientsRefused` | Relay refuses to send to the recipient (open-relay rules). |
| Mail accepted but never arrives | Greylisting, SPF/DKIM/DMARC failure on `EMAIL_FROM`, spam filter. Check the relay's logs. |

### 5.4 Unauthenticated internal relay

If your `SMTP_USER` is empty in `.env`, the daemon skips `server.login()` entirely. Useful for an internal Postfix that accepts mail from trusted source IPs:

```ini
SMTP_SERVER=mail.corp.local
SMTP_PORT=25
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=fortiwarn@corp.local
EMAIL_TO=noc@corp.local
```

(Pydantic still requires `SMTP_PASSWORD` to be present in the file — leave it as an empty string.)

### 5.5 Customising the alert templates

Both HTML bodies live under `fortivarn/views/templates/`:

| Template | Purpose |
|---|---|
| `switch_alert.html` | Failover detected — traffic now on backup. |
| `backup_down_alert.html` | Backup is down while main still up — redundancy lost. |

Each template receives the same three Jinja2 variables:

| Variable | Type | Example |
|---|---|---|
| `timestamp` | `str` | `2026-04-29 14:32:01` |
| `main_interface` | `str` | `x2` |
| `backup_interface` | `str` | `x1` |

Edit the templates in place — no code changes needed. The daemon reloads them on every send.

## 6. Zabbix Integration

A one-shot status probe is provided for Zabbix agent ``UserParameter`` polling. It performs a single FortiOS health-check API call and prints one integer to stdout:

| Value | Symbolic name | Meaning |
|---|---|---|
| `0` | `HEALTHY` | Main up, backup up — full redundancy. |
| `1` | `ON_BACKUP` | Main DOWN, backup up — failover active. |
| `2` | `UNKNOWN` | Both down, or probe failed (API/network/auth error). |
| `3` | `DEGRADED` | Main up, backup DOWN — no failover capacity. |

Exit code is always `0` so the Zabbix item records the value rather than going "unsupported".

> The numeric ordering is intentional: `0` is OK, `1` is the most operationally severe (you're already on backup), `2` is unknown, and `3` was added later for the degraded state to preserve compatibility with anyone whose triggers pre-date that feature.

### 6.1 Manual test

Run the probe by hand on the host that has FortiWarn installed:

```bash
cd /home/<user>/fortiwarn
./venv/bin/python -m fortivarn.controllers.zabbix_check
# → 0   (main is up)
```

### 6.2 Zabbix agent — installation

If the agent is not yet installed on the FortiWarn host:

```bash
# Debian/Ubuntu
sudo apt install zabbix-agent2          # or zabbix-agent (classic)

# RHEL/Fedora
sudo dnf install zabbix-agent2
```

The classic agent reads `/etc/zabbix/zabbix_agentd.conf` + `/etc/zabbix/zabbix_agentd.d/*.conf`. Agent 2 reads `/etc/zabbix/zabbix_agent2.conf` + `/etc/zabbix/zabbix_agent2.d/*.conf`. The `UserParameter` syntax is identical.

### 6.3 Zabbix agent — base configuration

Edit the main agent config so it can reach your Zabbix server:

```ini
# /etc/zabbix/zabbix_agentd.conf  (or zabbix_agent2.conf)
Server=<zabbix-server-ip>             # passive checks: who may poll us
ServerActive=<zabbix-server-ip>       # active checks: where we push to
Hostname=fortiwarn-host               # MUST match the "Host name" field in the Zabbix UI
Include=/etc/zabbix/zabbix_agentd.d/*.conf
LogFile=/var/log/zabbix/zabbix_agentd.log
Timeout=10                            # raise from default 3s — FortiGate API call may exceed it
```

> **Important**: `Timeout` must be ≥ a few seconds because the probe makes a live HTTPS call to the FortiGate. The default 3 s is too short and will produce intermittent `ZBX_NOTSUPPORTED: Timeout while executing a shell script.`

### 6.4 Zabbix agent — UserParameter

Drop the FortiWarn UserParameter into its own file so package upgrades don't overwrite it:

```bash
sudo tee /etc/zabbix/zabbix_agentd.d/fortiwarn.conf >/dev/null <<'EOF'
# FortiWarn — SDWAN failover status probe
# 0 = main up, 1 = backup active, 2 = unknown/error
UserParameter=fortiwarn.sdwan.status,cd /home/<user>/fortiwarn && ./venv/bin/python -m fortivarn.controllers.zabbix_check 2>/dev/null
EOF
sudo systemctl restart zabbix-agent     # or zabbix-agent2
```

Permissions notes:
- The Zabbix agent runs as user `zabbix` by default. That user must be able to **read** `/home/<user>/fortiwarn/.env` and **execute** the venv Python.
- Quick fix: `sudo setfacl -R -m u:zabbix:rX /home/<user>/fortiwarn`
- Or move the project to `/opt/fortiwarn` and `chown -R zabbix:zabbix /opt/fortiwarn`.

### 6.5 Verify from the Zabbix server

From the Zabbix server (or any host with `zabbix_get` installed):

```bash
zabbix_get -s <agent-host-ip> -k fortiwarn.sdwan.status
# Expected output: 0  (or 1 / 2)
```

If you see `ZBX_NOTSUPPORTED`:

| Message | Cause |
|---|---|
| `Unsupported item key.` | UserParameter not loaded — restart the agent, check the include path. |
| `Timeout while executing a shell script.` | Raise `Timeout=` in `zabbix_agentd.conf` (see § 6.3). |
| `Permission denied` | The `zabbix` user cannot read `.env` or execute the venv. |
| Output is `2` always | The probe itself errors — run it manually as the `zabbix` user (`sudo -u zabbix ...`) to see the real exception. |

### 6.6 Zabbix server — host configuration

In the Zabbix frontend (**Configuration → Hosts**):

1. **Create host** (or open the existing one for the FortiWarn machine):
   - **Host name**: must match `Hostname=` from § 6.3.
   - **Interfaces**: add an *Agent* interface pointing to the FortiWarn host's IP, port `10050`.
   - **Templates**: optional — link `Linux by Zabbix agent` for base OS metrics.
   - **Host groups**: e.g. `Network/SDWAN`.

2. **Add the value mapping** (**Administration → General → Value mapping**, or **Data collection → Value mappings** in 6.4+):
   - Name: `FortiWarn SDWAN status`
   - Mappings:
     - `0` → `Healthy (main + backup up)`
     - `1` → `On backup (failover)`
     - `2` → `Unknown / both down`
     - `3` → `Degraded (backup down)`

3. **Add the item** (host → Items → Create item):
   - **Name**: `SDWAN active link`
   - **Type**: `Zabbix agent`
   - **Key**: `fortiwarn.sdwan.status`
   - **Type of information**: `Numeric (unsigned)`
   - **Update interval**: `1m`
   - **History storage period**: `7d` (or per your retention policy)
   - **Trends storage period**: `90d`
   - **Show value**: `FortiWarn SDWAN status` (the value mapping above)
   - **Applications / Tags**: `component: sdwan`

4. **Add triggers** (host → Triggers → Create trigger). Syntax shown for Zabbix 5.4+ (new expression syntax):

   - **Failover to backup** (high — operationally severe):
     - Name: `SDWAN failed over to backup link on {HOST.NAME}`
     - Severity: `High`
     - Expression: `last(/fortiwarn-host/fortiwarn.sdwan.status)=1`
     - Recovery expression: `last(/fortiwarn-host/fortiwarn.sdwan.status)=0`

   - **Backup link down — redundancy lost** (warning):
     - Name: `SDWAN backup link DOWN on {HOST.NAME} (no failover capacity)`
     - Severity: `Warning`
     - Expression: `last(/fortiwarn-host/fortiwarn.sdwan.status)=3`
     - Recovery expression: `last(/fortiwarn-host/fortiwarn.sdwan.status)=0`

   - **Status unknown** (high — likely both ISPs down or probe broken):
     - Name: `SDWAN status unknown on {HOST.NAME}`
     - Severity: `High`
     - Expression: `last(/fortiwarn-host/fortiwarn.sdwan.status)=2`
     - Generate problem: `Multiple` with a 5-minute condition to avoid flapping: `min(/fortiwarn-host/fortiwarn.sdwan.status,5m)=2`

   For Zabbix ≤ 5.0 (legacy `{host:key.func()}` syntax):
   ```
   {fortiwarn-host:fortiwarn.sdwan.status.last()}=1   # on backup
   {fortiwarn-host:fortiwarn.sdwan.status.last()}=3   # backup down (degraded)
   {fortiwarn-host:fortiwarn.sdwan.status.min(5m)}=2  # unknown / both down
   ```

5. **(Optional) Action / notification** (**Configuration → Actions → Trigger actions**):
   - Conditions: `Trigger severity ≥ Warning` AND `Host group = Network/SDWAN`.
   - Operations: send message via your media type (email, Slack, etc.) to the on-call user group.
   - This is independent from the FortiWarn email — Zabbix gives you escalation, acknowledgements, and a dashboard view; FortiWarn's own email is the immediate first signal.

### 6.7 Dashboard widget (optional)

Add a *Plain text* or *Item value* widget on your NOC dashboard:

- Item: `fortiwarn-host: SDWAN active link`
- Show value mapping: ✓
- Result: the dashboard reads **Main** / **Backup** / **Unknown** in real time.

## 7. Testing

```bash
source venv/bin/activate
export PYTHONPATH=$PYTHONPATH:.
pytest tests/
```

All 3 business-logic tests use mocked clients and pass without a live FortiGate connection.
