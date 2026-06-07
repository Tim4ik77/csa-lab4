from __future__ import annotations

import json
from pathlib import Path

from .errors import ProcessorError
from .io_device import MMIODevice
from .isa import DATA_MEMORY_SIZE, DATA_WORD_SIZE, to_i32, to_u32


class DataMemory:
    def __init__(self, initial: dict[int, int] | None = None, mmio: MMIODevice | None = None) -> None:
        self.cells: dict[int, int] = {}
        self.mmio = mmio
        for address, value in (initial or {}).items():
            self._validate_address(address)
            self.cells[address] = to_u32(value)

    def read(self, address: int) -> int:
        self._validate_address(address)
        if self.mmio is not None and self.mmio.is_mmio_address(address):
            return to_i32(self.mmio.read(address))
        return to_i32(self.cells.get(address, 0))

    def write(self, address: int, value: int) -> str | None:
        self._validate_address(address)
        if self.mmio is not None and self.mmio.is_mmio_address(address):
            return self.mmio.write(address, value)
        self.cells[address] = to_u32(value)
        return None

    def dump_json(self) -> dict[str, int]:
        return {f"0x{address:06X}": to_i32(value) for address, value in sorted(self.cells.items())}

    def _validate_address(self, address: int) -> None:
        if address < 0 or address >= DATA_MEMORY_SIZE:
            raise ProcessorError(f"memory out of range: 0x{address:06X}")
        if address % DATA_WORD_SIZE != 0:
            raise ProcessorError(f"unaligned memory access: 0x{address:06X}")


def load_data_json(path: str | Path) -> dict[int, int]:
    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)
    result: dict[int, int] = {}
    for key, value in data.items():
        address = int(key, 0) if isinstance(key, str) else int(key)
        result[address] = int(value)
    return result
