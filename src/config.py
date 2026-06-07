from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when machine configuration is invalid."""


DEFAULT_MMIO = {
    "input_data": 0,
    "input_status": 4,
    "output_data": 8,
    "input_overrun": 12,
}


@dataclass(frozen=True)
class MachineConfig:
    mmio: dict[str, int]

    @classmethod
    def from_dict(cls, data: dict) -> MachineConfig:
        if set(data) - {"mmio"}:
            unknown = ", ".join(sorted(set(data) - {"mmio"}))
            raise ConfigError(f"unsupported config keys: {unknown}")
        mmio = dict(DEFAULT_MMIO)
        mmio.update(data.get("mmio", {}))
        required = set(DEFAULT_MMIO)
        missing = required - set(mmio)
        if missing:
            raise ConfigError(f"missing mmio keys: {', '.join(sorted(missing))}")
        for name, address in mmio.items():
            if not isinstance(address, int):
                raise ConfigError(f"mmio address {name} must be integer")
            if address < 0 or address % 4 != 0:
                raise ConfigError(f"mmio address {name} must be non-negative and word-aligned")
        if len(set(mmio.values())) != len(mmio):
            raise ConfigError("mmio addresses must be unique")
        return cls(mmio=mmio)

    def to_dict(self) -> dict:
        return {"mmio": dict(self.mmio)}


def load_config(path: str | Path | None) -> MachineConfig:
    if path is None:
        return MachineConfig.from_dict({"mmio": DEFAULT_MMIO})
    with Path(path).open(encoding="utf-8") as file:
        return MachineConfig.from_dict(json.load(file))
