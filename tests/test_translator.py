import json
from pathlib import Path

import pytest

from src.config import MachineConfig
from src.parser import parse
from src.translator import TranslationError, translate_file, translate_program

CONFIG = MachineConfig.from_dict({"mmio": {"input_data": 0, "input_status": 4, "output_data": 8, "input_overrun": 12}})


def test_translator_writes_binary_and_sidecar_files(tmp_path: Path):
    source = tmp_path / "hello.lisp"
    output = tmp_path / "hello.bin"
    config = tmp_path / "machine_config.json"
    source.write_text(Path("examples/hello.lisp").read_text(encoding="utf-8"), encoding="utf-8")
    config.write_text(json.dumps(CONFIG.to_dict()), encoding="utf-8")

    result = translate_file(source, output, config)

    assert output.exists()
    assert output.stat().st_size == 4 * len(result.instructions)
    assert (tmp_path / "hello.bin.hex").exists()
    assert (tmp_path / "hello.data.json").exists()
    assert (tmp_path / "hello.symbols.json").exists()
    assert (tmp_path / "hello.ast.json").exists()
    assert output.read_bytes() != output.read_text(encoding="latin1").encode("ascii", errors="ignore")


def test_translator_entry_vectors_default_handler_and_ast():
    program = parse("(defconst IO_STATUS 4) (defun main () 0)")
    result = translate_program(program, CONFIG)

    assert result.hex_listing[0].endswith("JMP 0x000008")
    assert "default_input_handler" in result.symbols["labels"]
    assert result.ast_json["type"] == "program"
    assert any("IRET" in line for line in result.hex_listing)


def test_translator_on_input_and_no_overlap_with_mmio():
    program = parse(
        """
        (defconst IO_IN 0)
        (defconst IO_STATUS 4)
        (defconst IO_OUT 8)
        (defun main () (while 1 0))
        (on-input (begin (mem-set IO_OUT (mem-get IO_IN)) (mem-set IO_STATUS 0)))
        """
    )
    result = translate_program(program, CONFIG)

    assert "input_handler" in result.symbols["labels"]
    mmio_addresses = set(CONFIG.mmio.values())
    assert not (set(result.data_memory) & mmio_addresses)


def test_translator_rejects_missing_main_and_const_assignment():
    with pytest.raises(TranslationError):
        translate_program(parse("(defun f () 1)"), CONFIG)
    with pytest.raises(TranslationError):
        translate_program(parse("(defconst A 1) (defun main () (setq A 2))"), CONFIG)
