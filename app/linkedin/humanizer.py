from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from playwright.async_api import Page

from app.config import AppConfig
from app.storage.db import StorageRepository


class LimitReachedError(Exception):
    """Indica que o limite diário ou semanal foi atingido."""


@dataclass
class Humanizer:
    config: AppConfig
    storage: StorageRepository

    async def wait_between_actions(self) -> None:
        delay = random.uniform(self.config.delay_min_seconds, self.config.delay_max_seconds)
        await asyncio.sleep(delay)

    async def wait_short(self) -> None:
        await asyncio.sleep(random.uniform(1.0, 3.0))

    async def wait_page_load(self) -> None:
        await asyncio.sleep(random.uniform(2.0, 5.0))

    async def simulate_scroll(self, page: Page) -> None:
        scroll_amount = random.randint(300, 800)
        await page.mouse.wheel(0, scroll_amount)
        await asyncio.sleep(random.uniform(0.5, 1.5))

    def ensure_within_limits(self) -> None:
        daily_count = self.storage.count_invites_today()
        weekly_count = self.storage.count_invites_this_week()

        if daily_count >= self.config.daily_limit:
            raise LimitReachedError(
                f"Limite diário atingido ({daily_count}/{self.config.daily_limit})."
            )

        if weekly_count >= self.config.weekly_limit:
            raise LimitReachedError(
                f"Limite semanal atingido ({weekly_count}/{self.config.weekly_limit})."
            )

    def can_send_more(self) -> bool:
        try:
            self.ensure_within_limits()
            return True
        except LimitReachedError:
            return False
