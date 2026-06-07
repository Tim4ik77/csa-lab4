import pytest

from src.isa import (
    ADDRESS_MASK,
    AddressingMode,
    Instruction,
    ISAError,
    Opcode,
    decode_instruction,
    encode_instruction,
    fits_signed_immediate,
)


def test_encode_decode_all_opcodes():
    for opcode in Opcode:
        mode = AddressingMode.ABSOLUTE if opcode == Opcode.STORE else AddressingMode.IMMEDIATE
        instruction = Instruction(opcode, mode, 0x1234)
        decoded = decode_instruction(instruction.encode())
        assert decoded.opcode == opcode
        assert decoded.mode == mode
        assert decoded.operand_raw == 0x1234


def test_encode_decode_all_modes():
    for mode in AddressingMode:
        decoded = decode_instruction(encode_instruction(Opcode.LOAD, mode, 0x20))
        assert decoded.mode == mode
        assert decoded.operand_raw == 0x20


def test_signed_immediate_and_operand_mask():
    instruction = decode_instruction(encode_instruction(Opcode.LOAD, AddressingMode.IMMEDIATE, -1))
    assert instruction.operand_raw == ADDRESS_MASK
    assert instruction.operand_signed == -1
    assert fits_signed_immediate(-(1 << 21))
    assert not fits_signed_immediate(1 << 21)


def test_invalid_opcode_and_store_immediate():
    with pytest.raises(ISAError):
        decode_instruction(0xFF000000)
    with pytest.raises(ISAError):
        encode_instruction(Opcode.STORE, AddressingMode.IMMEDIATE, 1)
