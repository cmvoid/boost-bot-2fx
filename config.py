"""Load and validate configuration from environment variables (.env)."""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# Default authorized users (used if AUTHORIZED_USER_IDS is empty in .env).
DEFAULT_AUTHORIZED_USER_IDS = {8494222081, 7639762965}


def _parse_id_list(raw: Optional[str]) -> set[int]:
    if not raw:
        return set()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


@dataclass
class Config:
    telegram_bot_token: str
    smm_api_url: str
    smm_api_key: str
    authorized_user_ids: set[int] = field(default_factory=set)
    balance_low_threshold: float = 5.0
    balance_check_interval_min: int = 30

    @classmethod
    def load(cls) -> "Config":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        api_url = os.getenv("SMM_API_URL", "").strip()
        api_key = os.getenv("SMM_API_KEY", "").strip()

        missing = []
        if not token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not api_url:
            missing.append("SMM_API_URL")
        if not api_key:
            missing.append("SMM_API_KEY")
        if missing:
            raise RuntimeError(
                "Missing configuration in the .env file: "
                + ", ".join(missing)
                + ".\nOpen the .env file and fill in the required values."
            )

        authorized = _parse_id_list(os.getenv("AUTHORIZED_USER_IDS"))
        if not authorized:
            authorized = set(DEFAULT_AUTHORIZED_USER_IDS)

        try:
            threshold = float(os.getenv("BALANCE_LOW_THRESHOLD", "5") or "5")
        except ValueError:
            threshold = 5.0

        try:
            interval = int(os.getenv("BALANCE_CHECK_INTERVAL_MIN", "30") or "30")
        except ValueError:
            interval = 30

        return cls(
            telegram_bot_token=token,
            smm_api_url=api_url,
            smm_api_key=api_key,
            authorized_user_ids=authorized,
            balance_low_threshold=threshold,
            balance_check_interval_min=max(1, interval),
        )
