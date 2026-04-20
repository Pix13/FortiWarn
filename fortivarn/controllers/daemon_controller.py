import asyncio
import logging
from fortivarn.config.settings import FortiWarnSettings
from fortivarn.models.fortinet_client import FortinetClient
from fortivarn.services.sdwan_service import SDWANMonitorService
from fortivarn.views.email_service import EmailService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

class DaemonController:
    def __init__(self):
        try:
            self.settings = FortiWarnSettings()
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            raise

        self.client = FortinetClient(self.settings)
        self.sdwan_service = SDWANMonitorService(
            client=self.client,
            main_iface=self.settings.main_interface,
            backup_iface=self.settings.backup_interface
        )
        self.email_service = EmailService(self.settings)
        
        # Track state to avoid spamming emails every interval if the switch persists
        self.is_on_backup = False

    async def run(self):
        logger.info("FortiWarn daemon starting...")
        logger.info(f"Monitoring interfaces: {self.settings.main_interface} <-> {self.settings.backup_interface}")
        
        try:
            async with self.client:
                while True:
                    await self._check_cycle()
                    await asyncio.sleep(self.settings.check_interval_seconds)
        except asyncio.CancelledError:
            logger.info("Daemon stopping...")
        except Exception as e:
            logger.exception(f"Unexpected error in daemon loop: {e}")
        finally:
            logger.info("FortiWarn daemon stopped.")

    async def _check_cycle(self):
        try:
            switch_detected = await self.sdwan_service.check_connection_switch()
            
            if switch_detected and not self.is_on_backup:
                # Transition from Main to Backup detected
                logger.warning("SDWAN Switch Detected! Connection moved to backup.")
                await self.email_service.send_switch_alert(
                    self.settings.main_interface, 
                    self.settings.backup_interface
                )
                self.is_on_backup = True
            
            elif not switch_detected and self.is_on_backup:
                # Transition from Backup back to Main detected
                logger.info("SDWAN Connection restored to main interface.")
                self.is_on_backup = False
            
            else:
                if not switch_detected:
                    logger.debug("Connection is stable on main interface.")
                else:
                    logger.debug("Connection remains on backup interface.")

        except Exception as e:
            logger.error(f"Error during check cycle: {e}")

if __name__ == "__main__":
    controller = DaemonController()
    try:
        asyncio.run(controller.run())
    except KeyboardInterrupt:
        pass
