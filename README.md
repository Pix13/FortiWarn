# FortiWarn

FortiWarn is a Python-based daemon designed to monitor Fortinet HA pairs for SDWAN connection switches. It detects when an internet connection transitions from a primary interface to a backup interface and sends an email alert via HTML templates.

## 🏗 Architecture (MVC)

The project follows the **Model-View-Controller (MVC)** design pattern with dependency injection:

-   **Models**:
    - `fortinet_client.py`: Asynchronous HTTP client using `httpx` to interact with FortiOS APIs. Supports both API Key and Basic Authentication.
    - `schemas.py`: Pydantic models for strict validation of interface status and SDWAN monitoring data.
    - `settings.py`: Configuration management via `pydantic-settings`.
-   **Views**:
    - `email_service.py`: Handles email dispatching using `smtplib` and `jinja2`.
    - `templates/`: HTML templates for professional, formatted alert emails.
-   **Services**:
    - `sdwan_service.py`: Contains the core business logic to determine if a connection switch has occurred based on interface status and SDWAN state. Uses a Protocol to allow easy mocking during testing.
-   **Controllers**:
    - `daemon_controller.py`: The main orchestrator that runs the infinite monitoring loop, manages state (to prevent alert spamming), and coordinates between services.

## 🚀 Installation & Setup

### 1. Prerequisites
- Python 3.9+
- Access to a Fortinet HA pair with API access enabled.
- SMTP server details for email notifications.

### 2. Clone and Install Dependencies
```bash
# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory based on the provided template:
```bash
cp .env.example .env
```

Edit `.env` with your specific credentials and interface names:
```ini
# Fortinet Credentials
FORTINET_HOST=your-fortigate-ip
FORTINET_USERNAME=admin
FORTINET_PASSWORD=yourpassword
# OR use API Key
# FORTINET_API_KEY=yourkey

# SDWAN Interface Names
MAIN_INTERFACE=wan1
BACKUP_INTERFACE=wan2

# Email Settings
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=app-password
EMAIL_FROM=fortivarn@example.com
EMAIL_TO=admin@example.com

# Daemon Settings
CHECK_INTERVAL_SECONDS=60
```

## 🛠 Running the Daemon

To start monitoring:
```bash
export PYTHONPATH=$PYTHONPATH:.
python fortivarn/controllers/daemon_controller.py
```

## 🧪 Testing

The project uses `pytest` for unit testing. The service layer is tested using mocks to simulate various Fortinet API responses.

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
export PYTHONPATH=$PYTHONPATH:.
pytest tests/
```

## 🛡 Security & Best Practices
- **Secrets**: Never commit `.env` files. Always use the provided `.env.example`.
- **Validation**: All incoming API data and environment variables are validated via Pydantic to prevent runtime errors from malformed input.
- **Alerting**: The daemon tracks state (`is_on_backup`) to ensure you only receive one email when a switch occurs, rather than an email every minute while the backup is active.
