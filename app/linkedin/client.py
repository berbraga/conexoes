from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

LINKEDIN_BASE_URL = "https://www.linkedin.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class LinkedInClient:
    def __init__(self, li_at_cookie: str) -> None:
        self._li_at_cookie = li_at_cookie
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[Page]:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="pt-BR",
        )
        await self._context.add_cookies(
            [
                {
                    "name": "li_at",
                    "value": self._li_at_cookie,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None",
                }
            ]
        )
        page = await self._context.new_page()
        try:
            await page.goto(f"{LINKEDIN_BASE_URL}/feed/", wait_until="domcontentloaded", timeout=60000)
            if "login" in page.url or "checkpoint" in page.url:
                raise RuntimeError("Cookie li_at inválido ou sessão expirada.")
            yield page
        finally:
            await self._close()

    async def _close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
