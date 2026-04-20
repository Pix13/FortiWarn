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

### 1.2 API Key Authentication (Recommended)

Generate a permanent API key for an admin user:

1. Go to **System > Administrators**, select your admin profile, and check **Enable API Key**.
2. The GUI generates a key like: `aBcD-eFgH-iJkL-mNop`.

> Store this value in the `.env` variable `FORTINET_API_KEY`.

### 1.3 Username / Password Authentication (Fallback)

If not using an API key, set `FORTINET_USERNAME` and `FORTINET_PASSWORD` instead of `FORTINET_API_KEY`. The admin account must have **super_admin** or equivalent policy-based permissions.

### 1.4 VDOM Considerations

If your FortiGate runs in multi-VDOM mode, the current code does not yet pass a `vdom` parameter to API calls — this is tracked as a medium-priority improvement. Ensure the admin user has access to all VDOMs or configure the relevant settings when that fix lands.

### 1.5 Firewall Rules

Ensure your server running FortiWarn can reach the FortiGate:

```bash
curl -k https://<FORTINET_HOST>/api/v2/authentication \
     -X POST \
     -H 'Content-Type: application/json' \
     -d '{"secretkey": "<API_KEY>", "request_key": true}' \
     2>&1 | python -m json.tool
```

The response should contain a `session_key`. If not, check that:
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

1. The daemon logs into the FortiGate (`/api/v2/authentication`) and obtains a session token.
2. Every interval, it queries:
   - SDWAN member status via `/api/v2/monitor/system/sdwan/member` (for interface health checks)
   - Same endpoint for backup member verification
3. A switch is detected if the main member reports down **or** if the backup member reports up while main was previously active.
4. When the connection returns to normal, internal state resets — no redundant email is sent.

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

## 5. Testing

```bash
source venv/bin/activate
export PYTHONPATH=$PYTHONPATH:.
pytest tests/
```

All 3 business-logic tests use mocked clients and pass without a live FortiGate connection.
