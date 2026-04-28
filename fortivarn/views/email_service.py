import smtplib
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from typing import Any, Dict
from fortivarn.config.settings import FortiWarnSettings

class EmailService:
    def __init__(self, settings: FortiWarnSettings):
        self.settings = settings
        self.env = Environment(
            loader=FileSystemLoader("fortivarn/views/templates")
        )

    async def send_switch_alert(self, main_iface: str, backup_iface: str) -> None:
        """
        Sends an email alert using the switch_alert template.
        """
        template = self.env.get_template("switch_alert.html")
        body = template.render(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            main_interface=main_iface,
            backup_interface=backup_iface
        )

        msg = EmailMessage()
        msg["Subject"] = "ALERT: SDWAN Connection Switched to Backup"
        msg["From"] = self.settings.email_from
        msg["To"] = self.settings.email_to
        msg.set_content("Please check the attached HTML alert for details.", subtype="html")
        msg.add_alternative(body, subtype="html")

        # In a real daemon, this would be async or run in a thread to not block the main loop
        try:
            with smtplib.SMTP(self.settings.smtp_server, self.settings.smtp_port) as server:
                if self.settings.smtp_port != 587 and self.settings.smtp_port != 465:
                    # Assume plain SMTP for non-standard ports if not specified otherwise
                    pass 
                else:
                    server.starttls()
                
                if self.settings.smtp_user:
                    server.login(self.settings.smtp_user, self.settings.smtp_password.get_secret_value())
                
                server.send_message(msg)
        except Exception as e:
            # In production, we'd use a proper logger here
            print(f"Failed to send email alert: {e}")
            raise e
