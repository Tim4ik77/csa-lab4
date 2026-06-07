import json
from pathlib import Path

import pytest

from src.isa import read_binary
from src.machine import Machine
from src.memory import load_data_json
from src.translator import translate_file


@pytest.mark.parametrize("golden_path", sorted(Path("golden").glob("*.yml")))
def test_golden_programs(golden_path: Path, tmp_path: Path):
    golden = json.loads(golden_path.read_text(encoding="utf-8"))

    config_path = tmp_path / f"{golden['name']}.config.json"
    source_path = tmp_path / f"{golden['name']}.lisp"
    output_path = tmp_path / f"{golden['name']}.bin"

    config_path.write_text(json.dumps(golden["config"]), encoding="utf-8")
    source_path.write_text(golden["source"], encoding="utf-8")

    result = translate_file(source_path, output_path, config_path)

    assert result.hex_listing == golden["machine_code_hex"]

    generated_data = {f"0x{address:06X}": value for address, value in result.data_memory.items()}
    assert generated_data == golden["data_memory"]

    machine = Machine(
        read_binary(output_path),
        load_data_json(output_path.with_suffix(".data.json")),
        config_path=config_path,
        input_events=golden["input"],
    )
    output = machine.run(golden["max_ticks"], fail_on_max_ticks=golden["fail_on_max_ticks"])

    assert output == golden["output"]
    log_text = "\n".join(machine.log_lines)

    for excerpt in golden["log_excerpt"]:
        assert excerpt.startswith("TICK ")
        assert excerpt in log_text
