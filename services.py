"""Map of boosting services offered by the bot.

Each entry links a friendly command (e.g. /members) to an SMM panel service ID.
You can find the service IDs:
  - in the SMM panel ("Services" section), or
  - by running the /panelservices command in the bot (shows the raw list from the panel).

IMPORTANT: replace the `service_id` values below with the REAL ones from your panel.
You can add/remove entries freely: the bot creates one command per entry.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BoostService:
    command: str          # Telegram command (without /), e.g. "members"
    service_id: int       # SMM panel service ID
    label: str            # human-readable name shown to the user
    min_quantity: int = 1 # minimum quantity (check the limits on the panel)
    max_quantity: int = 1_000_000
    price_info: str = ""  # price info shown to the user


# Real services offered by the client. Each requires a link and a quantity.
SERVICES: list[BoostService] = [
    # price 0.104$/1k
    BoostService(command="views",     service_id=6172, label="Telegram Post Views + Shares", price_info="0.104$/1k"),
    # price 0.2535$/1k
    BoostService(command="members",   service_id=3890, label="Telegram Channel Members", price_info="0.2535$/1k"),
    # price 0.0892$/1k
    BoostService(command="reactions", service_id=27,   label="Telegram Post Reactions", price_info="0.0892$/1k"),
]


def services_by_command() -> dict[str, BoostService]:
    return {s.command: s for s in SERVICES}
