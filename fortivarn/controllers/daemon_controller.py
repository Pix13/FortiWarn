import asyncio
import logging
from fortivarn.config.settings import FortiWarnSettings
from fortivarn.models.fortinet_client import FortinetClient
from fortivarn.services.sdwan_service import SDWANMonitorService, LinkState
from fortivarn.views.email_service import EmailService

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
            backup_iface=self.settings.backup_interface,
        )
        self.email_service = EmailService(self.settings)

        # Edge-trigger state — one alert per transition, not one per poll.
        self.is_on_backup = False
        self.is_backup_degraded = False

    async def run(self):
        logger.info("FortiWarn daemon starting...")
        logger.info(
            f"Monitoring interfaces: {self.settings.main_interface} <-> {self.settings.backup_interface}"
        )

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
            state = await self.sdwan_service.get_link_state()
            await self._handle_state(state)
        except Exception as e:
            logger.error(f"Error during check cycle: {e}")

    async def _handle_state(self, state: LinkState) -> None:
        main = self.settings.main_interface
        backup = self.settings.backup_interface

        # --- Failover edge (main down, backup up) ---
        if state == LinkState.ON_BACKUP and not self.is_on_backup:
            logger.warning("SDWAN Switch Detected! Connection moved to backup.")
            await self.email_service.send_switch_alert(main, backup)
            self.is_on_backup = True
        elif state != LinkState.ON_BACKUP and self.is_on_backup:
            logger.info("SDWAN connection restored to main interface.")
            self.is_on_backup = False

        # --- Degraded-redundancy edge (main up, backup down) ---
        if state == LinkState.DEGRADED_BACKUP_DOWN and not self.is_backup_degraded:
            logger.warning("SDWAN Backup Link Down — redundancy lost.")
            await self.email_service.send_backup_down_alert(main, backup)
            self.is_backup_degraded = True
        elif state != LinkState.DEGRADED_BACKUP_DOWN and self.is_backup_degraded:
            logger.info("SDWAN backup link recovered — redundancy restored.")
            self.is_backup_degraded = False

        if state == LinkState.HEALTHY:
            logger.debug("Both links healthy.")
        elif state == LinkState.BOTH_DOWN:
            logger.error("Both SDWAN links report down.")


if __name__ == "__main__":
    controller = DaemonController()
    try:
        asyncio.run(controller.run())
    except KeyboardInterrupt:
        pass
