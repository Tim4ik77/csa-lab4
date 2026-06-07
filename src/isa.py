from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

WORD_BITS = 32
WORD_MASK = 0xFFFFFFFF
SIGN_BIT_32 = 0x80000000
INSTRUCTION_SIZE = 4
DATA_WORD_SIZE = 4
ADDRESS_BITS = 22
ADDRESS_MASK = (1 << ADDRESS_BITS) - 1
DATA_MEMORY_SIZE = 1 << ADDRESS_BITS
STACK_START = DATA_MEMORY_SIZE
INT_VECTOR = 0x000004
PROGRAM_START = 0x000008

SIGNED_IMMEDIATE_MIN = -(1 << (ADDRESS_BITS - 1))
SIGNED_IMMEDIATE_MAX = (1 << (ADDRESS_BITS - 1)) - 1


class ISAError(ValueError):
    """Raised when an instruction word is invalid."""


class Opcode(IntEnum):
    HALT = 0x00
    LOAD = 0x01
    STORE = 0x02
    ADD = 0x03
    SUB = 0x04
    MUL = 0x05
    DIV = 0x06
    MOD = 0x07
    CMP = 0x08
    JMP = 0x09
    BEQ = 0x0A
    BNE = 0x0B
    BLT = 0x0C
    BLE = 0x0D
    BGT = 0x0E
    BGE = 0x0F
    PUSH = 0x10
    POP = 0x11
    CALL = 0x12
    RET = 0x13
    IRET = 0x14
    DROP = 0x15


class AddressingMode(IntEnum):
    IMMEDIATE = 0b00
    ABSOLUTE = 0b01
    INDIRECT = 0b10
    STACK_RELATIVE = 0b11


NO_OPERAND_OPCODES = {
    Opcode.HALT,
    Opcode.PUSH,
    Opcode.POP,
    Opcode.RET,
    Opcode.IRET,
    Opcode.DROP,
}

NO_MODE_OPCODES = {
    Opcode.HALT,
    Opcode.JMP,
    Opcode.BEQ,
    Opcode.BNE,
    Opcode.BLT,
    Opcode.BLE,
    Opcode.BGT,
    Opcode.BGE,
    Opcode.PUSH,
    Opcode.POP,
    Opcode.CALL,
    Opcode.RET,
    Opcode.IRET,
    Opcode.DROP,
}

BRANCH_OPCODES = {
    Opcode.JMP,
    Opcode.BEQ,
    Opcode.BNE,
    Opcode.BLT,
    Opcode.BLE,
    Opcode.BGT,
    Opcode.BGE,
}

ALU_OPCODES = {Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD}


@dataclass(frozen=True)
class Flags:
    n: bool = False
    z: bool = False
    v: bool = False
    c: bool = False

    def to_word(self) -> int:
        return (int(self.n) << 3) | (int(self.z) << 2) | (int(self.v) << 1) | int(self.c)

    @classmethod
    def from_word(cls, word: int) -> Flags:
        return cls(bool(word & 0x8), bool(word & 0x4), bool(word & 0x2), bool(word & 0x1))

    def __str__(self) -> str:
        return f"N{int(self.n)}Z{int(self.z)}V{int(self.v)}C{int(self.c)}"


@dataclass(frozen=True)
class Instruction:
    opcode: Opcode
    mode: AddressingMode = AddressingMode.IMMEDIATE
    operand: int = 0

    def encode(self) -> int:
        if self.opcode == Opcode.STORE and self.mode == AddressingMode.IMMEDIATE:
            raise ISAError("STORE immediate is forbidden")
        return encode_instruction(self.opcode, self.mode, self.operand)

    @property
    def operand_raw(self) -> int:
        return self.operand & ADDRESS_MASK

    @property
    def operand_signed(self) -> int:
        return sign_extend_22(self.operand_raw)

    def mnemonic(self) -> str:
        return format_instruction(self)


def to_u32(value: int) -> int:
    return value & WORD_MASK


def to_i32(value: int) -> int:
    value &= WORD_MASK
    if value & SIGN_BIT_32:
        return value - (1 << WORD_BITS)
    return value


def sign_extend_22(value: int) -> int:
    value &= ADDRESS_MASK
    sign_bit = 1 << (ADDRESS_BITS - 1)
    if value & sign_bit:
        return value - (1 << ADDRESS_BITS)
    return value


def fits_signed_immediate(value: int) -> bool:
    return SIGNED_IMMEDIATE_MIN <= value <= SIGNED_IMMEDIATE_MAX


def flags_from_result(result: int, overflow: bool = False, carry: bool = False) -> Flags:
    signed = to_i32(result)
    return Flags(n=signed < 0, z=signed == 0, v=overflow, c=carry)


def _coerce_opcode(opcode: int | Opcode) -> Opcode:
    try:
        return Opcode(opcode)
    except ValueError as exc:
        raise ISAError(f"unknown opcode: 0x{int(opcode):02X}") from exc


def _coerce_mode(mode: int | AddressingMode) -> AddressingMode:
    try:
        return AddressingMode(mode)
    except ValueError as exc:
        raise ISAError(f"invalid addressing mode: {mode}") from exc


def encode_instruction(
    opcode: int | Opcode,
    mode: int | AddressingMode = AddressingMode.IMMEDIATE,
    operand: int = 0,
) -> int:
    op = _coerce_opcode(opcode)
    addr_mode = _coerce_mode(mode)
    if op == Opcode.STORE and addr_mode == AddressingMode.IMMEDIATE:
        raise ISAError("STORE immediate is forbidden")
    return ((int(op) & 0xFF) << 24) | ((int(addr_mode) & 0x3) << 22) | (operand & ADDRESS_MASK)


def decode_instruction(word: int) -> Instruction:
    opcode_raw = (word >> 24) & 0xFF
    mode_raw = (word >> 22) & 0x3
    operand = word & ADDRESS_MASK
    opcode = _coerce_opcode(opcode_raw)
    mode = _coerce_mode(mode_raw)
    if opcode == Opcode.STORE and mode == AddressingMode.IMMEDIATE:
        raise ISAError("STORE immediate is forbidden")
    return Instruction(opcode, mode, operand)


def operand_to_text(mode: AddressingMode, operand: int) -> str:
    raw = operand & ADDRESS_MASK
    if mode == AddressingMode.IMMEDIATE:
        return f"#{sign_extend_22(raw)}"
    if mode == AddressingMode.ABSOLUTE:
        return f"0x{raw:06X}"
    if mode == AddressingMode.INDIRECT:
        return f"@0x{raw:06X}"
    if mode == AddressingMode.STACK_RELATIVE:
        return f"sp+{sign_extend_22(raw)}"
    raise ISAError(f"invalid addressing mode: {mode}")


def format_instruction(instruction: Instruction) -> str:
    opcode = instruction.opcode
    if opcode in NO_OPERAND_OPCODES:
        return opcode.name
    if opcode in BRANCH_OPCODES or opcode == Opcode.CALL:
        return f"{opcode.name} 0x{instruction.operand_raw:06X}"
    return f"{opcode.name} {operand_to_text(instruction.mode, instruction.operand)}"


def write_binary(path: str | Path, instructions: Iterable[Instruction]) -> None:
    with Path(path).open("wb") as file:
        for instruction in instructions:
            file.write(instruction.encode().to_bytes(4, byteorder="big", signed=False))


def read_binary(path: str | Path) -> list[int]:
    data = Path(path).read_bytes()
    if len(data) % 4 != 0:
        raise ISAError("machine code size is not a multiple of 4 bytes")
    return [int.from_bytes(data[index : index + 4], "big") for index in range(0, len(data), 4)]
