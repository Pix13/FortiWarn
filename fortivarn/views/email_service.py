import smtplib
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from fortivarn.config.settings import FortiWarnSettings


class EmailService:
    def __init__(self, settings: FortiWarnSettings):
        self.settings = settings
        self.env = Environment(
            loader=FileSystemLoader("fortivarn/views/templates")
        )

    async def send_switch_alert(self, main_iface: str, backup_iface: str) -> None:
        """Failover detected — main is down, traffic now on backup."""
        body = self._render(
            "switch_alert.html",
            main_interface=main_iface,
            backup_interface=backup_iface,
        )
        self._send("ALERT: SDWAN Connection Switched to Backup", body)

    async def send_backup_down_alert(self, main_iface: str, backup_iface: str) -> None:
        """Redundancy lost — main is still up, backup is down."""
        body = self._render(
            "backup_down_alert.html",
            main_interface=main_iface,
            backup_interface=backup_iface,
        )
        self._send("WARNING: SDWAN Backup Link Down — Redundancy Lost", body)

    # ------------------------------------------------------------------ helpers
    def _render(self, template_name: str, **ctx) -> str:
        template = self.env.get_template(template_name)
        return template.render(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **ctx,
        )

    def _send(self, subject: str, html_body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.settings.email_from
        msg["To"] = self.settings.email_to
        msg.set_content("Please check the attached HTML alert for details.", subtype="html")
        msg.add_alternative(html_body, subtype="html")

        try:
            with smtplib.SMTP(self.settings.smtp_server, self.settings.smtp_port) as server:
                if self.settings.smtp_port in (587, 465):
                    server.starttls()

                if self.settings.smtp_user:
                    server.login(
                        self.settings.smtp_user,
                        self.settings.smtp_password.get_secret_value(),
                    )

                server.send_message(msg)
        except Exception as e:
            print(f"Failed to send email alert: {e}")
            raise
