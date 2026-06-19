import json
from pathlib import Path

import pytest
import yaml

from src.isa import read_binary
from src.machine import Machine
from src.memory import load_data_json
from src.translator import translate_file

LOG_WINDOW = 500


def lines(value: list[str] | str) -> list[str]:
    if isinstance(value, str):
        return value.splitlines()
    return value


def data_memory(value: dict[str, int] | str) -> dict[str, int]:
    if isinstance(value, str):
        return {address: int(word) for address, word in (line.split(": ", maxsplit=1) for line in value.splitlines())}
    return value


@pytest.mark.parametrize("golden_path", sorted(Path("golden").glob("*.yml")))
def test_golden_programs(golden_path: Path, tmp_path: Path):
    golden = yaml.safe_load(golden_path.read_text(encoding="utf-8"))

    config_path = tmp_path / f"{golden['name']}.config.json"
    source_path = tmp_path / f"{golden['name']}.lisp"
    output_path = tmp_path / f"{golden['name']}.bin"

    config_path.write_text(json.dumps(golden["config"]), encoding="utf-8")
    source_path.write_text(golden["source"], encoding="utf-8")

    result = translate_file(source_path, output_path, config_path)

    assert result.hex_listing == lines(golden["machine_code_hex"])

    generated_data = {f"0x{address:06X}": value for address, value in result.data_memory.items()}
    assert generated_data == data_memory(golden["data_memory"])

    machine = Machine(
        read_binary(output_path),
        load_data_json(output_path.with_suffix(".data.json")),
        config_path=config_path,
        input_events=golden["input"],
    )
    output = machine.run(golden["max_ticks"], fail_on_max_ticks=golden["fail_on_max_ticks"])

    assert output == golden["output"]
    assert machine.log_lines[:LOG_WINDOW] == lines(golden["log"]["first_500"])
