from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import load_config
from .control_unit import ControlUnit, State
from .datapath import DataPath
from .errors import ProcessorError
from .io_device import MMIODevice, load_input_schedule
from .isa import format_instruction, read_binary
from .memory import DataMemory, load_data_json


class Machine:
    def __init__(
        self,
        instruction_words: list[int],
        data: dict[int, int],
        config_path: str | Path | None = None,
        input_events: Sequence[Sequence[Any]] | None = None,
    ) -> None:
        self.config = load_config(config_path)
        self.io = MMIODevice(self.config.mmio)
        self.io.load_input_schedule(input_events or [])
        self.memory = DataMemory(data, self.io)
        self.datapath = DataPath(instruction_words, self.memory)
        self.control_unit = ControlUnit(self.datapath)
        self.tick_counter = 0
        self.log_lines: list[str] = []

    def run(self, max_ticks: int = 100000, fail_on_max_ticks: bool = True) -> str:
        while self.tick_counter < max_ticks:
            irq, input_messages = self.io.process_tick(self.tick_counter)
            if irq:
                self.control_unit.request_interrupt()

            state = self.control_unit.state
            signals = self.control_unit.generate_control_signals()
            trace = self.datapath.apply(signals)
            self.control_unit.apply_control_signals(signals)
            self._log_tick(state, signals.active_names(), trace.memory, input_messages)
            self.tick_counter += 1
            self.control_unit.next_state()
            if state == State.HALT:
                return self.io.output()
        if fail_on_max_ticks:
            raise ProcessorError("max_ticks exceeded")
        return self.io.output()

    def _log_tick(self, state: State, signals: list[str], memory: list[str], inputs: list[str]) -> None:
        dp = self.datapath
        cu = self.control_unit

        parts = [
            f"TICK {self.tick_counter}",
            state.name,
            format_instruction(dp.IR),
            f"PC=0x{dp.PC:06X}",
            f"AR=0x{dp.AR:06X}",
            f"DR={dp.DR}",
            f"ACC={dp.ACC}",
            f"SP=0x{dp.SP:06X}",
            f"FLAGS={dp.FLAGS}",
            f"ISR={int(cu.IN_ISR)}",
            f"IRQ={int(cu.IRQ_PENDING)}",
            f"SIGNALS={','.join(signals) if signals else '-'}",
        ]

        if memory:
            parts.append(f"MEM={'|'.join(memory)}")

        if inputs:
            parts.append(f"INPUT={'|'.join(inputs)}")

        self.log_lines.append(" | ".join(parts))


def run_machine(
    code_path: str | Path,
    data_path: str | Path,
    input_path: str | Path | None,
    config_path: str | Path | None,
    log_path: str | Path | None,
    max_ticks: int,
) -> str:
    machine = Machine(
        read_binary(code_path),
        load_data_json(data_path),
        config_path=config_path,
        input_events=load_input_schedule(input_path),
    )
    output = machine.run(max_ticks=max_ticks, fail_on_max_ticks=True)
    if log_path is not None:
        Path(log_path).write_text("\n".join(machine.log_lines) + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Run the tick-by-tick processor model.")
    cli.add_argument("code")
    cli.add_argument("data")
    cli.add_argument("input")
    cli.add_argument("--config", default=None)
    cli.add_argument("--log", default=None)
    cli.add_argument("--max-ticks", type=int, default=100000)
    args = cli.parse_args(argv)
    output = run_machine(args.code, args.data, args.input, args.config, args.log, args.max_ticks)
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
