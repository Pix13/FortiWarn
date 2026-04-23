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

## 5. Testing

```bash
source venv/bin/activate
export PYTHONPATH=$PYTHONPATH:.
pytest tests/
```

All 3 business-logic tests use mocked clients and pass without a live FortiGate connection.
