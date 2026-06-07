import pytest

from src.config import MachineConfig
from src.control_unit import ControlUnit, State
from src.datapath import (
    ACCMux,
    ALUAMux,
    ALUBMux,
    ALUOp,
    ARMux,
    ControlSignals,
    DataPath,
)
from src.errors import ProcessorError
from src.io_device import MMIODevice
from src.isa import AddressingMode, Flags, Instruction, Opcode
from src.machine import Machine
from src.memory import DataMemory
from src.parser import parse
from src.translator import translate_program

CONFIG = {"mmio": {"input_data": 0, "input_status": 4, "output_data": 8, "input_overrun": 12}}


def encode_program(*instructions: Instruction) -> list[int]:
    return [instruction.encode() for instruction in instructions]


def test_datapath_mux_latches_alu_flags_and_memory():
    io = MMIODevice(CONFIG["mmio"])
    memory = DataMemory({16: 7}, io)
    datapath = DataPath(encode_program(Instruction(Opcode.LOAD, AddressingMode.IMMEDIATE, 5)), memory)

    datapath.apply(ControlSignals(imem_read=True, latch_ir=True))
    assert datapath.IR.opcode == Opcode.LOAD

    datapath.apply(ControlSignals(sel_acc_mux=ACCMux.IR_OPERAND, latch_acc=True))
    assert datapath.ACC == 5

    datapath.DR = 3
    datapath.apply(
        ControlSignals(
            sel_alu_a_mux=ALUAMux.ACC,
            sel_alu_b_mux=ALUBMux.DR,
            alu_op=ALUOp.SUB,
            sel_acc_mux=ACCMux.ALU_RESULT,
            latch_acc=True,
            latch_flags=True,
        )
    )
    assert datapath.ACC == 2
    assert Flags(n=False, z=False, v=False, c=True) == datapath.FLAGS

    datapath.apply(ControlSignals(sel_ar_mux=ARMux.IR_OPERAND, latch_ar=True))
    datapath.AR = 16
    datapath.apply(ControlSignals(dmem_read=True, latch_dr=True))
    assert datapath.DR == 7
    memory.write(8, ord("Z"))
    assert io.output() == "Z"


def test_control_unit_fetch_decode_branch_and_interrupt():
    datapath = DataPath(
        encode_program(Instruction(Opcode.LOAD, AddressingMode.IMMEDIATE, 1)),
        DataMemory({}),
    )
    cu = ControlUnit(datapath)

    assert cu.state == State.FETCH_IR
    datapath.apply(cu.generate_control_signals())
    cu.next_state()
    assert cu.state == State.FETCH_PC_INC
    datapath.apply(cu.generate_control_signals())
    cu.next_state()
    assert cu.state == State.DECODE
    cu.next_state()
    assert cu.state == State.LOAD_IMM

    datapath.FLAGS = Flags(z=True)
    datapath.IR = Instruction(Opcode.BEQ, operand=0x20)
    assert cu.evaluate_branch()
    datapath.IRQ_PENDING = True
    assert cu.evaluate_interrupt()


def test_machine_load_store_arithmetic_call_ret_and_output():
    source = """
    (defconst IO_OUT 8)
    (defvar x 2)
    (defun putc (ch) (mem-set IO_OUT ch))
    (defun inc (a) (+ a 1))
    (defun main ()
      (begin
        (setq x (inc x))
        (if (= x 3) (putc 'Y') (putc 'N'))))
    """
    result = translate_program(parse(source), MachineConfig.from_dict(CONFIG))
    machine = Machine(encode_program(*result.instructions), result.data_memory, input_events=[])

    assert machine.run(10000) == "Y"


def test_machine_direct_instruction_modes_push_pop_drop_and_branches():
    code = encode_program(
        Instruction(Opcode.LOAD, AddressingMode.ABSOLUTE, 16),
        Instruction(Opcode.PUSH),
        Instruction(Opcode.LOAD, AddressingMode.IMMEDIATE, 1),
        Instruction(Opcode.ADD, AddressingMode.STACK_RELATIVE, 0),
        Instruction(Opcode.DROP),
        Instruction(Opcode.CMP, AddressingMode.IMMEDIATE, 8),
        Instruction(Opcode.BNE, operand=36),
        Instruction(Opcode.STORE, AddressingMode.ABSOLUTE, 24),
        Instruction(Opcode.HALT),
        Instruction(Opcode.LOAD, AddressingMode.IMMEDIATE, 0),
        Instruction(Opcode.HALT),
    )
    machine = Machine(code, {16: 7, 20: 16, 24: 0}, input_events=[])

    machine.run(10000)
    assert machine.memory.read(24) == 8


def test_machine_trap_input_iret_and_overwrites_pending_char():
    source = """
    (defconst IO_IN 0)
    (defconst IO_STATUS 4)
    (defconst IO_OUT 8)
    (defun main () (while 1 0))
    (on-input (begin (mem-set IO_OUT (mem-get IO_IN)) (mem-set IO_STATUS 0)))
    """
    result = translate_program(parse(source), MachineConfig.from_dict(CONFIG))
    machine = Machine(
        encode_program(*result.instructions),
        result.data_memory,
        input_events=[[50, "a"], [51, "b"]],
    )

    assert machine.run(500, fail_on_max_ticks=False) == "b"
    assert machine.io.registers["input_overrun"] == 1
    assert machine.io.registers["input_data"] == ord("b")
    assert any("INT_SAVE_PC_DEC_SP" in line and "ISR=1" in line for line in machine.log_lines)


def test_machine_errors():
    with pytest.raises(ProcessorError, match="division by zero"):
        Machine(
            encode_program(
                Instruction(Opcode.LOAD, AddressingMode.IMMEDIATE, 1),
                Instruction(Opcode.DIV, AddressingMode.IMMEDIATE, 0),
                Instruction(Opcode.HALT),
            ),
            {},
            input_events=[],
        ).run(100)

    with pytest.raises(ProcessorError, match="stack underflow"):
        Machine(encode_program(Instruction(Opcode.POP), Instruction(Opcode.HALT)), {}, input_events=[]).run(100)
