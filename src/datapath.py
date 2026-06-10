from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .errors import ProcessorError
from .isa import (
    DATA_WORD_SIZE,
    INT_VECTOR,
    STACK_START,
    WORD_MASK,
    Flags,
    Instruction,
    Opcode,
    decode_instruction,
    flags_from_result,
    to_i32,
    to_u32,
)
from .memory import DataMemory


class PCMux(Enum):
    ALU_RESULT = auto()
    IR_OPERAND = auto()
    DR = auto()
    INT_VECTOR = auto()


class ARMux(Enum):
    IR_OPERAND = auto()
    DR = auto()
    SP = auto()
    ALU_RESULT = auto()


class DRMux(Enum):
    DMEM_DATA_OUT = auto()
    ACC = auto()
    PC = auto()
    FLAGS = auto()


class ACCMux(Enum):
    ALU_RESULT = auto()
    DR = auto()
    IR_OPERAND = auto()


class FlagsMux(Enum):
    ALU_NZVC = auto()
    DR = auto()


class ALUAMux(Enum):
    ACC = auto()
    SP = auto()
    PC = auto()


class ALUBMux(Enum):
    DR = auto()
    IR_OPERAND = auto()
    CONST_4 = auto()


class ALUOp(Enum):
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    MOD = auto()


@dataclass
class ControlSignals:
    sel_pc_mux: PCMux = PCMux.ALU_RESULT
    sel_ar_mux: ARMux = ARMux.IR_OPERAND
    sel_dr_mux: DRMux = DRMux.DMEM_DATA_OUT
    sel_acc_mux: ACCMux = ACCMux.ALU_RESULT
    sel_flags_mux: FlagsMux = FlagsMux.ALU_NZVC
    sel_alu_a_mux: ALUAMux = ALUAMux.ACC
    sel_alu_b_mux: ALUBMux = ALUBMux.DR
    alu_op: ALUOp = ALUOp.ADD

    latch_pc: bool = False
    latch_ir: bool = False
    latch_ar: bool = False
    latch_dr: bool = False
    latch_acc: bool = False
    latch_sp: bool = False
    latch_flags: bool = False

    imem_read: bool = False
    dmem_read: bool = False
    dmem_write: bool = False

    set_in_isr: bool = False
    clear_in_isr: bool = False
    clear_irq_pending: bool = False
    check_stack_pop: bool = False

    def active_names(self) -> list[str]:
        names: list[str] = []
        for field_name in (
            "imem_read",
            "dmem_read",
            "dmem_write",
            "latch_pc",
            "latch_ir",
            "latch_ar",
            "latch_dr",
            "latch_acc",
            "latch_sp",
            "latch_flags",
            "set_in_isr",
            "clear_in_isr",
            "clear_irq_pending",
            "check_stack_pop",
        ):
            if getattr(self, field_name):
                names.append(field_name)
        if any(
            getattr(self, name)
            for name in (
                "latch_pc",
                "latch_ar",
                "latch_dr",
                "latch_acc",
                "latch_sp",
                "latch_flags",
            )
        ):
            names.extend(
                [
                    f"pc_mux={self.sel_pc_mux.name}",
                    f"ar_mux={self.sel_ar_mux.name}",
                    f"dr_mux={self.sel_dr_mux.name}",
                    f"acc_mux={self.sel_acc_mux.name}",
                    f"alu={self.alu_op.name}",
                ]
            )
        return names


@dataclass
class TickTrace:
    memory: list[str] = field(default_factory=list)


class DataPath:
    def __init__(self, instruction_memory: list[int], data_memory: DataMemory) -> None:
        self.instruction_memory = instruction_memory
        self.data_memory = data_memory

        self.PC = 0x000000
        self.IR = Instruction(Opcode.HALT)
        self.AR = 0
        self.DR = 0
        self.ACC = 0
        self.SP = STACK_START
        self.FLAGS = Flags()

        self._imem_data_out = 0
        self._dmem_data_out = 0

    def apply(self, signals: ControlSignals) -> TickTrace:
        if signals.dmem_read and signals.dmem_write:
            raise ProcessorError("data memory is one-port: simultaneous read/write")

        if signals.check_stack_pop and self.SP >= STACK_START:
            raise ProcessorError("stack underflow")

        trace = TickTrace()
        alu_result, alu_flags = self._alu(signals)

        if signals.imem_read:
            self._imem_data_out = self.imem_read(self.PC)
            trace.memory.append(f"imem_read[0x{self.PC:06X}]=0x{self._imem_data_out:08X}")

        if signals.dmem_read:
            self._dmem_data_out = self.dmem_read(self.AR)
            trace.memory.append(f"dmem_read[0x{self.AR:06X}]={self._dmem_data_out}")

        if signals.dmem_write:
            message = self.dmem_write(self.AR, self.DR)
            trace.memory.append(f"dmem_write[0x{self.AR:06X}]={self.DR}")

            if message:
                trace.memory.append(message)

        next_pc = self._select_pc(signals, alu_result)
        next_ar = self._select_ar(signals, alu_result)
        next_dr = self._select_dr(signals)
        next_acc = self._select_acc(signals, alu_result)
        next_sp = alu_result
        next_flags = self._select_flags(signals, alu_flags)

        if signals.latch_pc:
            self.latch_pc(next_pc)

        if signals.latch_ir:
            self.latch_ir(self._imem_data_out)

        if signals.latch_ar:
            self.latch_ar(next_ar)

        if signals.latch_dr:
            self.latch_dr(next_dr)

        if signals.latch_acc:
            self.latch_acc(next_acc)

        if signals.latch_sp:
            self.latch_sp(next_sp)

        if signals.latch_flags:
            self.latch_flags(next_flags)

        return trace

    def imem_read(self, address: int) -> int:
        if address < 0 or address % DATA_WORD_SIZE != 0:
            raise ProcessorError(f"PC out of range: 0x{address:06X}")

        index = address // 4
        if index < 0 or index >= len(self.instruction_memory):
            raise ProcessorError(f"PC out of range: 0x{address:06X}")

        return self.instruction_memory[index]

    def dmem_read(self, address: int) -> int:
        return self.data_memory.read(address)

    def dmem_write(self, address: int, value: int) -> str | None:
        return self.data_memory.write(address, value)

    def latch_pc(self, value: int) -> None:
        if value < 0 or value % DATA_WORD_SIZE != 0:
            raise ProcessorError(f"PC out of range: 0x{value:06X}")
        self.PC = value

    def latch_ir(self, word: int) -> None:
        try:
            self.IR = decode_instruction(word)
        except ValueError as exc:
            raise ProcessorError(str(exc)) from exc

    def latch_ar(self, value: int) -> None:
        self.AR = value & WORD_MASK

    def latch_dr(self, value: int) -> None:
        self.DR = to_i32(value)

    def latch_acc(self, value: int) -> None:
        self.ACC = to_i32(value)

    def latch_sp(self, value: int) -> None:
        if value < 0:
            raise ProcessorError("stack overflow")

        if value > STACK_START:
            raise ProcessorError("stack underflow")

        if value % DATA_WORD_SIZE != 0:
            raise ProcessorError(f"unaligned stack pointer: 0x{value:06X}")

        self.SP = value

    def latch_flags(self, value: Flags) -> None:
        self.FLAGS = value

    def _select_pc(self, signals: ControlSignals, alu_result: int) -> int:
        if signals.sel_pc_mux == PCMux.ALU_RESULT:
            return alu_result
        if signals.sel_pc_mux == PCMux.IR_OPERAND:
            return self.IR.operand_raw
        if signals.sel_pc_mux == PCMux.DR:
            return self.DR & WORD_MASK
        if signals.sel_pc_mux == PCMux.INT_VECTOR:
            return INT_VECTOR
        raise ProcessorError("invalid PC mux")

    def _select_ar(self, signals: ControlSignals, alu_result: int) -> int:
        if signals.sel_ar_mux == ARMux.IR_OPERAND:
            return self.IR.operand_raw
        if signals.sel_ar_mux == ARMux.DR:
            return self.DR & WORD_MASK
        if signals.sel_ar_mux == ARMux.SP:
            return self.SP
        if signals.sel_ar_mux == ARMux.ALU_RESULT:
            return alu_result
        raise ProcessorError("invalid AR mux")

    def _select_dr(self, signals: ControlSignals) -> int:
        if signals.sel_dr_mux == DRMux.DMEM_DATA_OUT:
            return self._dmem_data_out
        if signals.sel_dr_mux == DRMux.ACC:
            return self.ACC
        if signals.sel_dr_mux == DRMux.PC:
            return self.PC
        if signals.sel_dr_mux == DRMux.FLAGS:
            return self.FLAGS.to_word()
        raise ProcessorError("invalid DR mux")

    def _select_acc(self, signals: ControlSignals, alu_result: int) -> int:
        if signals.sel_acc_mux == ACCMux.ALU_RESULT:
            return alu_result
        if signals.sel_acc_mux == ACCMux.DR:
            return self.DR
        if signals.sel_acc_mux == ACCMux.IR_OPERAND:
            return self.IR.operand_signed
        raise ProcessorError("invalid ACC mux")

    def _select_flags(self, signals: ControlSignals, alu_flags: Flags) -> Flags:
        if signals.sel_flags_mux == FlagsMux.ALU_NZVC:
            return alu_flags
        if signals.sel_flags_mux == FlagsMux.DR:
            return Flags.from_word(self.DR)
        raise ProcessorError("invalid FLAGS mux")

    def _select_alu_a(self, signals: ControlSignals) -> int:
        if signals.sel_alu_a_mux == ALUAMux.ACC:
            return self.ACC
        if signals.sel_alu_a_mux == ALUAMux.SP:
            return self.SP
        if signals.sel_alu_a_mux == ALUAMux.PC:
            return self.PC
        raise ProcessorError("invalid ALU A mux")

    def _select_alu_b(self, signals: ControlSignals) -> int:
        if signals.sel_alu_b_mux == ALUBMux.DR:
            return self.DR
        if signals.sel_alu_b_mux == ALUBMux.IR_OPERAND:
            return self.IR.operand_signed
        if signals.sel_alu_b_mux == ALUBMux.CONST_4:
            return 4
        raise ProcessorError("invalid ALU B mux")

    def _alu(self, signals: ControlSignals) -> tuple[int, Flags]:
        a = self._select_alu_a(signals)
        b = self._select_alu_b(signals)

        if signals.alu_op == ALUOp.ADD:
            raw = to_u32(a) + to_u32(b)
            result = to_i32(raw)
            signed_result = to_i32(a) + to_i32(b)
            overflow = signed_result < -(1 << 31) or signed_result > (1 << 31) - 1
            carry = raw > WORD_MASK
            return result, flags_from_result(result, overflow, carry)

        if signals.alu_op == ALUOp.SUB:
            raw = to_u32(a) - to_u32(b)
            result = to_i32(raw)
            signed_result = to_i32(a) - to_i32(b)
            overflow = signed_result < -(1 << 31) or signed_result > (1 << 31) - 1
            carry = to_u32(a) >= to_u32(b)
            return result, flags_from_result(result, overflow, carry)

        if signals.alu_op == ALUOp.MUL:
            signed_result = to_i32(a) * to_i32(b)
            result = to_i32(signed_result)
            overflow = signed_result < -(1 << 31) or signed_result > (1 << 31) - 1
            return result, flags_from_result(result, overflow, False)

        if signals.alu_op == ALUOp.DIV:
            if b == 0:
                raise ProcessorError("division by zero")

            result = _trunc_div(to_i32(a), to_i32(b))
            return result, flags_from_result(result)

        if signals.alu_op == ALUOp.MOD:
            if b == 0:
                raise ProcessorError("division by zero")

            dividend = to_i32(a)
            divisor = to_i32(b)
            result = dividend - _trunc_div(dividend, divisor) * divisor
            return result, flags_from_result(result)

        raise ProcessorError("invalid ALU op")


def _trunc_div(a: int, b: int) -> int:
    sign = -1 if (a < 0) ^ (b < 0) else 1
    return sign * (abs(a) // abs(b))
