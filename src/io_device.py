from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .isa import to_u32


@dataclass
class InputEvent:
    tick: int
    char: str


@dataclass
class MMIODevice:
    mapping: dict[str, int]
    registers: dict[str, int] = field(default_factory=dict)
    output_buffer: list[str] = field(default_factory=list)
    input_events: list[InputEvent] = field(default_factory=list)
    _event_index: int = 0

    def __post_init__(self) -> None:
        for name in self.mapping:
            self.registers.setdefault(name, 0)

    def is_mmio_address(self, address: int) -> bool:
        return address in self._reverse_mapping()

    def read(self, address: int) -> int:
        name = self._name_for_address(address)
        return self.registers.get(name, 0)

    def write(self, address: int, value: int) -> str | None:
        name = self._name_for_address(address)
        value = to_u32(value)
        self.registers[name] = value
        if name == "output_data":
            char = chr(value & 0xFF)
            self.output_buffer.append(char)
            return f"output '{_escape_char(char)}'"
        return None

    def load_input_schedule(self, events: Sequence[Sequence[Any]]) -> None:
        schedule: list[InputEvent] = []
        for item in events:
            if len(item) != 2:
                raise ValueError("input event must be [tick, char]")
            tick, char = item
            if not isinstance(tick, int) or tick < 0:
                raise ValueError("input tick must be a non-negative integer")
            if not isinstance(char, str) or len(char) != 1:
                raise ValueError("input char must be a one-character string")
            schedule.append(InputEvent(tick, char))
        self.input_events = sorted(schedule, key=lambda event: event.tick)
        self._event_index = 0

    def process_tick(self, tick: int) -> tuple[bool, list[str]]:
        irq = False
        messages: list[str] = []
        while self._event_index < len(self.input_events) and self.input_events[self._event_index].tick == tick:
            event = self.input_events[self._event_index]
            self._event_index += 1
            if self.registers.get("input_status", 0) == 0:
                self.registers["input_data"] = ord(event.char)
                self.registers["input_status"] = 1
                irq = True
                messages.append(f"input '{_escape_char(event.char)}'")
            else:
                self.registers["input_data"] = ord(event.char)
                self.registers["input_overrun"] = 1
                messages.append(f"input overrun '{_escape_char(event.char)}'")
        return irq, messages

    def output(self) -> str:
        return "".join(self.output_buffer)

    def _name_for_address(self, address: int) -> str:
        reverse = self._reverse_mapping()
        if address not in reverse:
            raise KeyError(address)
        return reverse[address]

    def _reverse_mapping(self) -> dict[int, str]:
        return {address: name for name, address in self.mapping.items()}


def _escape_char(char: str) -> str:
    return char.encode("unicode_escape").decode("ascii")


def load_input_schedule(path: str | Path | None) -> list[list[Any]]:
    if path is None:
        return []
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)
