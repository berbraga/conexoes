from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlparse

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from app.config import AppConfig
from app.linkedin.client import LinkedInClient
from app.linkedin.humanizer import Humanizer, LimitReachedError
from app.storage.db import StorageRepository

logger = logging.getLogger(__name__)

CONNECT_BUTTON_PATTERNS = re.compile(
    r"conectar|connect|convidar|invite",
    re.IGNORECASE,
)
SEND_BUTTON_PATTERNS = re.compile(
    r"enviar|send|convidar|invite",
    re.IGNORECASE,
)
ADD_NOTE_PATTERNS = re.compile(
    r"adicionar uma nota|add a note|personalizar convite|personalize invite",
    re.IGNORECASE,
)


@dataclass
class ConnectionResult:
    sent_count: int = 0
    skipped_count: int = 0
    finished: bool = False
    stop_reason: str = ""


@dataclass
class ConnectionWorker:
    config: AppConfig
    storage: StorageRepository
    stop_requested: Callable[[], bool] = field(default=lambda: False)

    def __post_init__(self) -> None:
        self._humanizer = Humanizer(config=self.config, storage=self.storage)

    async def run(self) -> ConnectionResult:
        result = ConnectionResult()
        run_id = self.storage.start_run()

        try:
            client = LinkedInClient(self.config.li_at_cookie)
            async with client.session() as page:
                await self._process_search(page, result)

            status = "completed" if result.finished else "stopped"
            self.storage.finish_run(
                run_id,
                status=status,
                sent_count=result.sent_count,
                skipped_count=result.skipped_count,
            )
        except LimitReachedError as error:
            result.stop_reason = str(error)
            result.finished = True
            self.storage.finish_run(
                run_id,
                status="limit_reached",
                sent_count=result.sent_count,
                skipped_count=result.skipped_count,
                error_message=str(error),
            )
        except Exception as error:
            result.stop_reason = str(error)
            logger.exception("Erro durante execução do worker")
            self.storage.finish_run(
                run_id,
                status="error",
                sent_count=result.sent_count,
                skipped_count=result.skipped_count,
                error_message=str(error),
            )
            raise

        return result

    async def _process_search(self, page: Page, result: ConnectionResult) -> None:
        await page.goto(self.config.search_url, wait_until="domcontentloaded", timeout=60000)
        await self._humanizer.wait_page_load()

        page_number = 1
        while not self.stop_requested():
            if not self._humanizer.can_send_more():
                raise LimitReachedError("Limite de convites atingido.")

            cards = await self._collect_profile_cards(page)
            if not cards:
                result.finished = True
                result.stop_reason = "Nenhum perfil encontrado na página atual."
                break

            for card in cards:
                if self.stop_requested():
                    result.stop_reason = "Execução interrompida pelo usuário."
                    return

                if not self._humanizer.can_send_more():
                    raise LimitReachedError("Limite de convites atingido.")

                profile_url, profile_name = await self._extract_profile_info(card)
                if not profile_url:
                    result.skipped_count += 1
                    continue

                if self.storage.was_invited(profile_url):
                    logger.info("Perfil já convidado: %s", profile_url)
                    result.skipped_count += 1
                    continue

                sent = await self._send_invite(page, card, profile_name)
                if sent:
                    self.storage.register_invite(profile_url, profile_name)
                    result.sent_count += 1
                    logger.info("Convite enviado para %s", profile_name)
                    await self._humanizer.wait_between_actions()
                else:
                    result.skipped_count += 1

            if self.stop_requested():
                result.stop_reason = "Execução interrompida pelo usuário."
                return

            has_next = await self._go_to_next_page(page)
            if not has_next:
                result.finished = True
                result.stop_reason = "Lista de conexões finalizada."
                break

            page_number += 1
            logger.info("Avançando para página %s", page_number)
            await self._humanizer.wait_page_load()

    async def _collect_profile_cards(self, page: Page) -> list[Locator]:
        selectors = [
            "div[data-chameleon-result-urn]",
            "li.reusable-search__result-container",
            "div.entity-result",
        ]
        for selector in selectors:
            cards = page.locator(selector)
            count = await cards.count()
            if count > 0:
                return [cards.nth(index) for index in range(count)]
        return []

    async def _extract_profile_info(self, card: Locator) -> tuple[str, str]:
        link = card.locator('a[href*="/in/"]').first
        if await link.count() == 0:
            return "", ""

        href = await link.get_attribute("href") or ""
        profile_url = self._normalize_profile_url(href)

        name = ""
        aria_label = await link.get_attribute("aria-label")
        if aria_label:
            name = aria_label.strip()
        else:
            name_element = card.locator(
                "span[dir='ltr'] span[aria-hidden='true'], "
                ".entity-result__title-text a span[aria-hidden='true']"
            ).first
            if await name_element.count() > 0:
                name = (await name_element.inner_text()).strip()

        if not name:
            name = "conexão"

        first_name = name.split()[0] if name else "conexão"
        return profile_url, first_name

    async def _send_invite(self, page: Page, card: Locator, profile_name: str) -> bool:
        connect_button = await self._find_button_in_card(card, CONNECT_BUTTON_PATTERNS)
        if connect_button is None:
            return False

        try:
            await connect_button.scroll_into_view_if_needed()
            await self._humanizer.wait_short()
            await connect_button.click()
            await self._humanizer.wait_short()
        except PlaywrightTimeoutError:
            return False

        note = self.config.note_template.format(nome=profile_name)
        added_note = await self._add_note_if_possible(page, note)
        if not added_note and "{nome}" in self.config.note_template:
            await self._dismiss_modal(page)
            return False

        send_button = await self._find_button_in_page(page, SEND_BUTTON_PATTERNS)
        if send_button is None:
            await self._dismiss_modal(page)
            return False

        try:
            await send_button.click()
            await self._humanizer.wait_short()
            return True
        except PlaywrightTimeoutError:
            await self._dismiss_modal(page)
            return False

    async def _add_note_if_possible(self, page: Page, note: str) -> bool:
        add_note_button = await self._find_button_in_page(page, ADD_NOTE_PATTERNS)
        if add_note_button is None:
            return True

        try:
            await add_note_button.click()
            await self._humanizer.wait_short()
        except PlaywrightTimeoutError:
            return False

        textarea = page.locator(
            "textarea[name='message'], textarea#custom-message, textarea"
        ).first
        if await textarea.count() == 0:
            return False

        await textarea.fill(note[:300])
        await self._humanizer.wait_short()
        return True

    async def _find_button_in_card(self, card: Locator, pattern: re.Pattern) -> Locator | None:
        buttons = card.locator("button")
        count = await buttons.count()
        for index in range(count):
            button = buttons.nth(index)
            label = await self._button_label(button)
            if pattern.search(label):
                return button
        return None

    async def _find_button_in_page(self, page: Page, pattern: re.Pattern) -> Locator | None:
        buttons = page.locator("button")
        count = await buttons.count()
        for index in range(count):
            button = buttons.nth(index)
            label = await self._button_label(button)
            if pattern.search(label):
                return button
        return None

    async def _button_label(self, button: Locator) -> str:
        parts: list[str] = []
        for attribute in ("aria-label", "data-control-name"):
            value = await button.get_attribute(attribute)
            if value:
                parts.append(value)
        text = (await button.inner_text()).strip()
        if text:
            parts.append(text)
        return " ".join(parts)

    async def _dismiss_modal(self, page: Page) -> None:
        dismiss_selectors = [
            "button[aria-label='Dismiss']",
            "button[aria-label='Fechar']",
            "button.artdeco-modal__dismiss",
        ]
        for selector in dismiss_selectors:
            button = page.locator(selector).first
            if await button.count() > 0:
                try:
                    await button.click()
                    await asyncio.sleep(0.5)
                    return
                except PlaywrightTimeoutError:
                    continue

    async def _go_to_next_page(self, page: Page) -> bool:
        next_button = page.locator(
            "button[aria-label='Próxima'], button[aria-label='Next'], "
            "button.artdeco-pagination__button--next"
        ).first
        if await next_button.count() == 0:
            return False

        disabled = await next_button.get_attribute("disabled")
        if disabled is not None:
            return False

        await next_button.scroll_into_view_if_needed()
        await self._humanizer.simulate_scroll(page)
        await next_button.click()
        await page.wait_for_load_state("domcontentloaded")
        return True

    def _normalize_profile_url(self, href: str) -> str:
        absolute = urljoin("https://www.linkedin.com", href)
        parsed = urlparse(absolute)
        path = parsed.path.rstrip("/")
        match = re.match(r"(/in/[^/]+)", path)
        if match:
            return f"https://www.linkedin.com{match.group(1)}"
        return absolute.split("?")[0]
