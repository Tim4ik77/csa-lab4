from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import ast
from .config import MachineConfig, load_config
from .isa import (
    AddressingMode,
    Instruction,
    Opcode,
    fits_signed_immediate,
    format_instruction,
    to_i32,
    to_u32,
    write_binary,
)
from .parser import parse_file


class TranslationError(ValueError):
    """Raised when a program cannot be translated."""


@dataclass
class SymbolInfo:
    name: str
    kind: str
    address: int
    size: int = 1
    value: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "address": self.address,
            "size": self.size,
            "value": self.value,
        }


@dataclass
class AsmInstruction:
    opcode: Opcode
    mode: AddressingMode = AddressingMode.IMMEDIATE
    operand: int | str = 0


@dataclass
class TranslationResult:
    instructions: list[Instruction]
    data_memory: dict[int, int]
    symbols: dict[str, Any]
    ast_json: dict[str, Any]
    hex_listing: list[str]


class DataAllocator:
    def __init__(self, mmio_addresses: list[int]) -> None:
        self.occupied = set(mmio_addresses)
        self.cursor = self._align(max(self.occupied) + 4 if self.occupied else 0)
        self.program_data_start = self.cursor
        self.memory: dict[int, int] = {}
        self.symbols: dict[str, SymbolInfo] = {}

    @staticmethod
    def _align(address: int) -> int:
        return (address + 3) & ~0x3

    def allocate(self, name: str, kind: str, values: list[int], value: int | str | None = None) -> int:
        if name in self.symbols:
            raise TranslationError(f"duplicate data symbol: {name}")

        base = self._find_free_block(len(values))

        for offset, word in enumerate(values):
            address = base + offset * 4
            self.occupied.add(address)
            self.memory[address] = to_u32(word)

        self.symbols[name] = SymbolInfo(name=name, kind=kind, address=base, size=len(values), value=value)
        return base

    def allocate_anonymous(self, kind: str, values: list[int], value: int | str | None = None) -> int:
        name = f"__{kind}_{len(self.symbols)}"
        return self.allocate(name, kind, values, value)

    def _find_free_block(self, words: int) -> int:
        address = self._align(self.cursor)

        if words == 0:
            words = 1

        while True:
            block = {address + index * 4 for index in range(words)}

            if not (block & self.occupied):
                self.cursor = address + words * 4
                return address

            address += 4

    def to_json_memory(self) -> dict[int, int]:
        return {address: to_i32(value) for address, value in sorted(self.memory.items())}


class Assembler:
    def __init__(self) -> None:
        self.items: list[AsmInstruction] = []
        self.labels: dict[str, int] = {}

    def label(self, name: str) -> None:
        if name in self.labels:
            raise TranslationError(f"duplicate label: {name}")
        self.labels[name] = len(self.items) * 4

    def emit(
        self,
        opcode: Opcode,
        mode: AddressingMode = AddressingMode.IMMEDIATE,
        operand: int | str = 0,
    ) -> None:
        self.items.append(AsmInstruction(opcode, mode, operand))

    def assemble(self) -> list[Instruction]:
        instructions: list[Instruction] = []

        for item in self.items:
            operand = self._resolve_operand(item.operand)
            instructions.append(Instruction(item.opcode, item.mode, operand))

        return instructions

    def _resolve_operand(self, operand: int | str) -> int:
        if isinstance(operand, int):
            return operand

        if operand not in self.labels:
            raise TranslationError(f"unknown label: {operand}")

        return self.labels[operand]


class Compiler:
    def __init__(self, program: ast.Program, config: MachineConfig) -> None:
        self.program = program
        self.config = config
        self.functions = program.functions()
        self.function_arities = {name: len(fn.parameters) for name, fn in self.functions.items()}
        self.allocator = DataAllocator(list(config.mmio.values()))
        self.asm = Assembler()
        self.current_function: ast.Defun | None = None
        self.current_scope = ""
        self.label_counter = 0
        self.addr_tmp_by_scope: dict[str, int] = {}

    def translate(self) -> TranslationResult:
        if "main" not in self.functions:
            raise TranslationError("entry point (defun main ...) is required")
        self._collect_data()
        handler = self.program.on_input()
        handler_label = "input_handler" if handler is not None else "default_input_handler"

        self.asm.emit(Opcode.JMP, operand="main")
        self.asm.emit(Opcode.JMP, operand=handler_label)

        for form in self.program.forms:
            if isinstance(form, ast.Defun):
                self._compile_function(form)

        if handler is None:
            self._compile_default_input_handler(handler_label)
        else:
            self._compile_input_handler(handler_label, handler)

        instructions = self.asm.assemble()
        hex_listing = [
            f"0x{address:06X} - {instruction.encode():08X} - {format_instruction(instruction)}"
            for address, instruction in enumerate_by_address(instructions)
        ]

        symbols = {
            "program_data_start": self.allocator.program_data_start,
            "data": {name: info.to_dict() for name, info in sorted(self.allocator.symbols.items())},
            "functions": {name: self.asm.labels[name] for name in sorted(self.functions)},
            "labels": dict(sorted(self.asm.labels.items())),
            "mmio": dict(self.config.mmio),
        }
        return TranslationResult(
            instructions=instructions,
            data_memory=self.allocator.to_json_memory(),
            symbols=symbols,
            ast_json=self.program.to_dict(),
            hex_listing=hex_listing,
        )

    def _collect_data(self) -> None:
        seen_functions = set(self.functions)

        for form in self.program.forms:
            if isinstance(form, (ast.DefConst, ast.DefVar, ast.DefBuffer)) and form.name in seen_functions:
                raise TranslationError(f"data symbol conflicts with function name: {form.name}")

            if isinstance(form, ast.DefConst):
                initial = self._literal_initial_value(form.value)
                self.allocator.allocate(form.name, "const", [initial], self._literal_public_value(form.value))

            elif isinstance(form, ast.DefVar):
                initial = self._literal_initial_value(form.value)
                self.allocator.allocate(form.name, "var", [initial], self._literal_public_value(form.value))

            elif isinstance(form, ast.DefBuffer):
                self.allocator.allocate(form.name, "buffer", [0] * form.size, form.size)

    def _literal_initial_value(self, literal: ast.Literal) -> int:
        if literal.kind == "integer":
            return int(literal.value)

        if literal.kind == "char":
            return int(literal.value)

        if literal.kind == "string":
            return self._allocate_cstr(str(literal.value))

        raise TranslationError(f"unsupported literal kind: {literal.kind}")

    @staticmethod
    def _literal_public_value(literal: ast.Literal) -> int | str:
        return literal.value

    def _allocate_cstr(self, value: str) -> int:
        words = [ord(char) for char in value] + [0]
        return self.allocator.allocate_anonymous("string", words, value)

    def _compile_function(self, function: ast.Defun) -> None:
        self.current_function = function
        self.current_scope = function.name
        self.asm.label(function.name)
        self._compile_sequence(function.body, temp_depth=0)
        self.asm.emit(Opcode.HALT if function.name == "main" else Opcode.RET)
        self.current_function = None
        self.current_scope = ""

    def _compile_input_handler(self, label: str, handler: ast.OnInput) -> None:
        self.current_function = None
        self.current_scope = label
        self.asm.label(label)
        self._compile_sequence(handler.body, temp_depth=0)
        self.asm.emit(Opcode.IRET)
        self.current_scope = ""

    def _compile_default_input_handler(self, label: str) -> None:
        self.asm.label(label)
        self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, 0)
        self.asm.emit(Opcode.STORE, AddressingMode.ABSOLUTE, self.config.mmio["input_status"])
        self.asm.emit(Opcode.IRET)

    def _compile_sequence(self, expressions: list[ast.Expr], temp_depth: int) -> None:
        if not expressions:
            self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, 0)
            return

        for expression in expressions:
            self._compile_expr(expression, temp_depth)

    def _compile_expr(self, expression: ast.Expr, temp_depth: int) -> None:
        if isinstance(expression, ast.Literal):
            self._compile_literal(expression)
        elif isinstance(expression, ast.Symbol):
            self._compile_symbol(expression.name, temp_depth)
        elif isinstance(expression, ast.Begin):
            self._compile_sequence(expression.expressions, temp_depth)
        elif isinstance(expression, ast.Setq):
            self._compile_setq(expression, temp_depth)
        elif isinstance(expression, ast.If):
            self._compile_if(expression, temp_depth)
        elif isinstance(expression, ast.While):
            self._compile_while(expression, temp_depth)
        elif isinstance(expression, ast.BinaryOp):
            self._compile_binary(expression, temp_depth)
        elif isinstance(expression, ast.Compare):
            self._compile_compare(expression, temp_depth)
        elif isinstance(expression, ast.MemGet):
            self._compile_mem_get(expression, temp_depth)
        elif isinstance(expression, ast.MemSet):
            self._compile_mem_set(expression, temp_depth)
        elif isinstance(expression, ast.Call):
            self._compile_call(expression, temp_depth)
        else:
            raise TranslationError(f"unsupported expression: {expression!r}")

    def _compile_literal(self, literal: ast.Literal) -> None:
        if literal.kind == "integer":
            value = int(literal.value)
            if fits_signed_immediate(value):
                self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, value)
            else:
                address = self.allocator.allocate_anonymous("integer", [value], value)
                self.asm.emit(Opcode.LOAD, AddressingMode.ABSOLUTE, address)
        elif literal.kind == "char":
            self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, int(literal.value))
        elif literal.kind == "string":
            self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, self._allocate_cstr(str(literal.value)))
        else:
            raise TranslationError(f"unsupported literal kind: {literal.kind}")

    def _compile_symbol(self, name: str, temp_depth: int) -> None:
        param_offset = self._parameter_offset(name, temp_depth)
        if param_offset is not None:
            self.asm.emit(Opcode.LOAD, AddressingMode.STACK_RELATIVE, param_offset)
            return
        if name not in self.allocator.symbols:
            raise TranslationError(f"unknown symbol: {name}")
        symbol = self.allocator.symbols[name]
        if symbol.kind == "buffer":
            self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, symbol.address)
        else:
            self.asm.emit(Opcode.LOAD, AddressingMode.ABSOLUTE, symbol.address)

    def _compile_setq(self, expression: ast.Setq, temp_depth: int) -> None:
        if expression.name in self.allocator.symbols and self.allocator.symbols[expression.name].kind == "const":
            raise TranslationError(f"cannot assign to constant: {expression.name}")

        self._compile_expr(expression.expression, temp_depth)

        param_offset = self._parameter_offset(expression.name, temp_depth)
        if param_offset is not None:
            self.asm.emit(Opcode.STORE, AddressingMode.STACK_RELATIVE, param_offset)
            return

        symbol = self.allocator.symbols.get(expression.name)
        if symbol is None:
            raise TranslationError(f"unknown variable: {expression.name}")

        if symbol.kind != "var":
            raise TranslationError(f"cannot assign to {symbol.kind}: {expression.name}")

        self.asm.emit(Opcode.STORE, AddressingMode.ABSOLUTE, symbol.address)

    def _compile_if(self, expression: ast.If, temp_depth: int) -> None:
        else_label = self._new_label("else")
        end_label = self._new_label("endif")
        self._compile_expr(expression.condition, temp_depth)
        self.asm.emit(Opcode.CMP, AddressingMode.IMMEDIATE, 0)
        self.asm.emit(Opcode.BEQ, operand=else_label)
        self._compile_expr(expression.then_branch, temp_depth)
        self.asm.emit(Opcode.JMP, operand=end_label)
        self.asm.label(else_label)
        self._compile_expr(expression.else_branch, temp_depth)
        self.asm.label(end_label)

    def _compile_while(self, expression: ast.While, temp_depth: int) -> None:
        start_label = self._new_label("while")
        end_label = self._new_label("endwhile")
        self.asm.label(start_label)
        self._compile_expr(expression.condition, temp_depth)
        self.asm.emit(Opcode.CMP, AddressingMode.IMMEDIATE, 0)
        self.asm.emit(Opcode.BEQ, operand=end_label)
        self._compile_sequence(expression.body, temp_depth)
        self.asm.emit(Opcode.JMP, operand=start_label)
        self.asm.label(end_label)
        self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, 0)

    def _compile_binary(self, expression: ast.BinaryOp, temp_depth: int) -> None:
        opcode = {
            "+": Opcode.ADD,
            "-": Opcode.SUB,
            "*": Opcode.MUL,
            "/": Opcode.DIV,
            "mod": Opcode.MOD,
        }[expression.operator]
        self._compile_expr(expression.right, temp_depth)
        self.asm.emit(Opcode.PUSH)
        self._compile_expr(expression.left, temp_depth + 1)
        self.asm.emit(opcode, AddressingMode.STACK_RELATIVE, 0)
        self.asm.emit(Opcode.DROP)

    def _compile_compare(self, expression: ast.Compare, temp_depth: int) -> None:
        true_label = self._new_label("cmp_true")
        end_label = self._new_label("cmp_end")
        branch_opcode = {
            "=": Opcode.BEQ,
            "!=": Opcode.BNE,
            "<": Opcode.BLT,
            "<=": Opcode.BLE,
            ">": Opcode.BGT,
            ">=": Opcode.BGE,
        }[expression.operator]
        self._compile_expr(expression.right, temp_depth)
        self.asm.emit(Opcode.PUSH)
        self._compile_expr(expression.left, temp_depth + 1)
        self.asm.emit(Opcode.CMP, AddressingMode.STACK_RELATIVE, 0)
        self.asm.emit(Opcode.DROP)
        self.asm.emit(branch_opcode, operand=true_label)
        self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, 0)
        self.asm.emit(Opcode.JMP, operand=end_label)
        self.asm.label(true_label)
        self.asm.emit(Opcode.LOAD, AddressingMode.IMMEDIATE, 1)
        self.asm.label(end_label)

    def _compile_mem_get(self, expression: ast.MemGet, temp_depth: int) -> None:
        self._compile_expr(expression.address, temp_depth)
        addr_tmp = self._current_addr_tmp()
        self.asm.emit(Opcode.STORE, AddressingMode.ABSOLUTE, addr_tmp)
        self.asm.emit(Opcode.LOAD, AddressingMode.INDIRECT, addr_tmp)

    def _compile_mem_set(self, expression: ast.MemSet, temp_depth: int) -> None:
        self._compile_expr(expression.value, temp_depth)
        self.asm.emit(Opcode.PUSH)
        self._compile_expr(expression.address, temp_depth + 1)
        addr_tmp = self._current_addr_tmp()
        self.asm.emit(Opcode.STORE, AddressingMode.ABSOLUTE, addr_tmp)
        self.asm.emit(Opcode.POP)
        self.asm.emit(Opcode.STORE, AddressingMode.INDIRECT, addr_tmp)

    def _compile_call(self, expression: ast.Call, temp_depth: int) -> None:
        if expression.name not in self.functions:
            raise TranslationError(f"unknown function: {expression.name}")

        expected = self.function_arities[expression.name]
        if expected != len(expression.arguments):
            raise TranslationError(
                f"function {expression.name} expects {expected} arguments, got {len(expression.arguments)}"
            )

        depth = temp_depth
        for argument in expression.arguments:
            self._compile_expr(argument, depth)
            self.asm.emit(Opcode.PUSH)
            depth += 1

        self.asm.emit(Opcode.CALL, operand=expression.name)

        for _ in expression.arguments:
            self.asm.emit(Opcode.DROP)
            depth -= 1

    def _parameter_offset(self, name: str, temp_depth: int) -> int | None:
        if self.current_function is None:
            return None

        try:
            index = self.current_function.parameters.index(name)
        except ValueError:
            return None

        base_offset = 4 * (len(self.current_function.parameters) - index)
        return base_offset + 4 * temp_depth

    def _new_label(self, prefix: str) -> str:
        self.label_counter += 1
        return f"__{prefix}_{self.label_counter}"

    def _current_addr_tmp(self) -> int:
        scope = self.current_scope or "global"
        if scope not in self.addr_tmp_by_scope:
            name = "__addr_tmp" if scope == "main" else f"__addr_tmp_{scope}"
            self.addr_tmp_by_scope[scope] = self.allocator.allocate(name, "temp", [0], 0)
        return self.addr_tmp_by_scope[scope]


def enumerate_by_address(instructions: list[Instruction]) -> list[tuple[int, Instruction]]:
    return [(index * 4, instruction) for index, instruction in enumerate(instructions)]


def translate_program(program: ast.Program, config: MachineConfig) -> TranslationResult:
    return Compiler(program, config).translate()


def write_translation_outputs(result: TranslationResult, output_bin: str | Path) -> None:
    output = Path(output_bin)
    write_binary(output, result.instructions)
    output.with_name(output.name + ".hex").write_text("\n".join(result.hex_listing) + "\n", encoding="utf-8")
    output.with_suffix(".data.json").write_text(
        json.dumps({f"0x{address:06X}": value for address, value in result.data_memory.items()}, indent=2),
        encoding="utf-8",
    )
    output.with_suffix(".symbols.json").write_text(
        json.dumps(result.symbols, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    output.with_suffix(".ast.json").write_text(
        json.dumps(result.ast_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def translate_file(
    source: str | Path,
    output_bin: str | Path,
    config_path: str | Path | None = None,
) -> TranslationResult:
    program = parse_file(source)
    result = translate_program(program, load_config(config_path))
    write_translation_outputs(result, output_bin)
    return result


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Translate Lisp-like source to binary machine code.")
    cli.add_argument("source")
    cli.add_argument("output")
    cli.add_argument("--config", default=None)
    args = cli.parse_args(argv)
    translate_file(args.source, args.output, args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
