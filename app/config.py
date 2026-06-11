from __future__ import annotations

import json
from enum import IntEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, field_validator

DATA_DIR = Path("/app/data")
CONFIG_PATH = DATA_DIR / "config.json"


class Weekday(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


WEEKDAY_LABELS = {
    Weekday.MONDAY: "Segunda",
    Weekday.TUESDAY: "Terça",
    Weekday.WEDNESDAY: "Quarta",
    Weekday.THURSDAY: "Quinta",
    Weekday.FRIDAY: "Sexta",
    Weekday.SATURDAY: "Sábado",
    Weekday.SUNDAY: "Domingo",
}


class AppConfig(BaseModel):
    li_at_cookie: str = ""
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    run_time: str = "09:00"
    search_url: str = ""
    note_template: str = "Olá {nome}, gostaria de me conectar com você."
    daily_limit: int = Field(default=15, ge=1, le=50)
    weekly_limit: int = Field(default=100, ge=1, le=300)
    delay_min_seconds: int = Field(default=20, ge=5, le=300)
    delay_max_seconds: int = Field(default=60, ge=10, le=600)
    scheduler_enabled: bool = False

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        for day in value:
            if day < 0 or day > 6:
                raise ValueError("Dias da semana devem estar entre 0 (segunda) e 6 (domingo).")
        return sorted(set(value))

    @field_validator("run_time")
    @classmethod
    def validate_run_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Horário deve estar no formato HH:MM.")
        hour, minute = int(parts[0]), int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Horário inválido.")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("delay_max_seconds")
    @classmethod
    def validate_delay_range(cls, value: int, info) -> int:
        delay_min = info.data.get("delay_min_seconds", 20)
        if value < delay_min:
            raise ValueError("Delay máximo deve ser maior ou igual ao mínimo.")
        return value

    @field_validator("search_url")
    @classmethod
    def validate_search_url(cls, value: str) -> str:
        if value and "linkedin.com" not in value:
            raise ValueError("URL deve ser do LinkedIn.")
        return value.strip()

    def is_ready(self) -> bool:
        return bool(self.li_at_cookie and self.search_url and self.note_template)

    @classmethod
    def load(cls) -> Self:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists():
            config = cls()
            config.save()
            return config
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            return cls.model_validate(json.load(file))

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(self.model_dump(), file, indent=2, ensure_ascii=False)
