from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .datapath import (
    ACCMux,
    ALUAMux,
    ALUBMux,
    ALUOp,
    ARMux,
    ControlSignals,
    DataPath,
    DRMux,
    FlagsMux,
    PCMux,
)
from .errors import ProcessorError
from .isa import ALU_OPCODES, BRANCH_OPCODES, AddressingMode, Flags, Instruction, Opcode


class State(Enum):
    FETCH_IR = auto()
    FETCH_PC_INC = auto()
    DECODE = auto()

    LOAD_IMM = auto()
    LOAD_ADDR = auto()
    LOAD_MEM = auto()
    LOAD_INDIRECT_ADDR = auto()
    LOAD_INDIRECT_MEM = auto()
    LOAD_WB = auto()

    STORE_ADDR = auto()
    STORE_INDIRECT_READ = auto()
    STORE_INDIRECT_ADDR = auto()
    STORE_PREPARE = auto()
    STORE_MEM = auto()

    ALU_ADDR = auto()
    ALU_MEM = auto()
    ALU_INDIRECT_ADDR = auto()
    ALU_INDIRECT_MEM = auto()
    ALU_EXEC = auto()

    CMP_ADDR = auto()
    CMP_MEM = auto()
    CMP_INDIRECT_ADDR = auto()
    CMP_INDIRECT_MEM = auto()
    CMP_EXEC = auto()

    JUMP_EXEC = auto()
    BRANCH_EXEC = auto()

    PUSH_DEC_SP = auto()
    PUSH_WRITE_ADDR = auto()
    PUSH_WRITE_DATA = auto()
    PUSH_MEM = auto()

    POP_ADDR = auto()
    POP_READ = auto()
    POP_WB = auto()

    DROP_INC_SP = auto()

    CALL_DEC_SP = auto()
    CALL_SAVE_PC = auto()
    CALL_WRITE = auto()
    CALL_JUMP = auto()

    RET_ADDR = auto()
    RET_READ = auto()
    RET_JUMP = auto()
    RET_INC_SP = auto()

    INT_SAVE_PC_DEC_SP = auto()
    INT_SAVE_PC_WRITE = auto()
    INT_SAVE_PC_MEM = auto()
    INT_SAVE_FLAGS_DEC_SP = auto()
    INT_SAVE_FLAGS_WRITE = auto()
    INT_SAVE_FLAGS_MEM = auto()
    INT_SAVE_ACC_DEC_SP = auto()
    INT_SAVE_ACC_WRITE = auto()
    INT_SAVE_ACC_MEM = auto()
    INT_JUMP_VECTOR = auto()

    IRET_RESTORE_ACC_ADDR = auto()
    IRET_RESTORE_ACC_READ = auto()
    IRET_RESTORE_ACC_WB = auto()
    IRET_RESTORE_FLAGS_ADDR = auto()
    IRET_RESTORE_FLAGS_READ = auto()
    IRET_RESTORE_FLAGS_WB = auto()
    IRET_RESTORE_PC_ADDR = auto()
    IRET_RESTORE_PC_READ = auto()
    IRET_RESTORE_PC_WB = auto()

    HALT = auto()


ADDRESS_SETUP_STATES = {
    State.LOAD_ADDR,
    State.STORE_ADDR,
    State.ALU_ADDR,
    State.CMP_ADDR,
}

READ_TO_DR_STATES = {
    State.LOAD_MEM,
    State.LOAD_INDIRECT_MEM,
    State.STORE_INDIRECT_READ,
    State.ALU_MEM,
    State.ALU_INDIRECT_MEM,
    State.CMP_MEM,
    State.CMP_INDIRECT_MEM,
}

DR_TO_AR_STATES = {
    State.LOAD_INDIRECT_ADDR,
    State.STORE_INDIRECT_ADDR,
    State.ALU_INDIRECT_ADDR,
    State.CMP_INDIRECT_ADDR,
}

IRET_ADDR_STATES = {
    State.IRET_RESTORE_ACC_ADDR,
    State.IRET_RESTORE_FLAGS_ADDR,
    State.IRET_RESTORE_PC_ADDR,
}

IRET_READ_STATES = {
    State.IRET_RESTORE_ACC_READ,
    State.IRET_RESTORE_FLAGS_READ,
    State.IRET_RESTORE_PC_READ,
}


class InstructionDecoder:
    def decode(self, instruction: Instruction) -> State:
        opcode = instruction.opcode

        if opcode == Opcode.HALT:
            return State.HALT

        if opcode == Opcode.LOAD:
            return State.LOAD_IMM if instruction.mode == AddressingMode.IMMEDIATE else State.LOAD_ADDR

        if opcode == Opcode.STORE:
            if instruction.mode == AddressingMode.IMMEDIATE:
                raise ProcessorError("STORE immediate")
            return State.STORE_ADDR

        if opcode in ALU_OPCODES:
            return State.ALU_EXEC if instruction.mode == AddressingMode.IMMEDIATE else State.ALU_ADDR

        if opcode == Opcode.CMP:
            return State.CMP_EXEC if instruction.mode == AddressingMode.IMMEDIATE else State.CMP_ADDR

        if opcode == Opcode.JMP:
            return State.JUMP_EXEC

        if opcode in BRANCH_OPCODES:
            return State.BRANCH_EXEC

        if opcode == Opcode.PUSH:
            return State.PUSH_DEC_SP

        if opcode == Opcode.POP:
            return State.POP_ADDR

        if opcode == Opcode.DROP:
            return State.DROP_INC_SP

        if opcode == Opcode.CALL:
            return State.CALL_DEC_SP

        if opcode == Opcode.RET:
            return State.RET_ADDR

        if opcode == Opcode.IRET:
            return State.IRET_RESTORE_ACC_ADDR

        raise ProcessorError(f"unknown opcode: {opcode}")


class BranchLogic:
    def evaluate(self, instruction: Instruction, flags: Flags) -> bool:
        opcode = instruction.opcode

        if opcode == Opcode.JMP:
            return True

        if opcode == Opcode.BEQ:
            return flags.z

        if opcode == Opcode.BNE:
            return not flags.z

        if opcode == Opcode.BLT:
            return flags.n != flags.v

        if opcode == Opcode.BLE:
            return flags.z or flags.n != flags.v

        if opcode == Opcode.BGT:
            return (not flags.z) and flags.n == flags.v

        if opcode == Opcode.BGE:
            return flags.n == flags.v

        return False


@dataclass
class InterruptController:
    in_isr: bool = False
    irq_pending: bool = False

    def request_interrupt(self) -> None:
        self.irq_pending = True

    def evaluate(self) -> bool:
        return self.irq_pending and not self.in_isr

    def apply_control_signals(self, signals: ControlSignals) -> None:
        if signals.set_in_isr:
            self.in_isr = True

        if signals.clear_in_isr:
            self.in_isr = False

        if signals.clear_irq_pending:
            self.irq_pending = False


class ControlSequencer:
    def __init__(self) -> None:
        self.state = State.FETCH_IR

    def next_state(self, mode: AddressingMode, decoded_state: State, interrupt_enter: bool) -> State:
        state = self.state

        if state == State.FETCH_IR:
            self.state = State.FETCH_PC_INC
        elif state == State.FETCH_PC_INC:
            self.state = State.DECODE
        elif state == State.DECODE:
            self.state = decoded_state

        elif state == State.LOAD_IMM:
            self.state = self._after_instruction(interrupt_enter)
        elif state == State.LOAD_ADDR:
            self.state = State.LOAD_MEM
        elif state == State.LOAD_MEM:
            self.state = State.LOAD_INDIRECT_ADDR if mode == AddressingMode.INDIRECT else State.LOAD_WB
        elif state == State.LOAD_INDIRECT_ADDR:
            self.state = State.LOAD_INDIRECT_MEM
        elif state == State.LOAD_INDIRECT_MEM:
            self.state = State.LOAD_WB
        elif state == State.LOAD_WB:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.STORE_ADDR:
            self.state = State.STORE_INDIRECT_READ if mode == AddressingMode.INDIRECT else State.STORE_PREPARE
        elif state == State.STORE_INDIRECT_READ:
            self.state = State.STORE_INDIRECT_ADDR
        elif state == State.STORE_INDIRECT_ADDR:
            self.state = State.STORE_PREPARE
        elif state == State.STORE_PREPARE:
            self.state = State.STORE_MEM
        elif state == State.STORE_MEM:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.ALU_ADDR:
            self.state = State.ALU_MEM
        elif state == State.ALU_MEM:
            self.state = State.ALU_INDIRECT_ADDR if mode == AddressingMode.INDIRECT else State.ALU_EXEC
        elif state == State.ALU_INDIRECT_ADDR:
            self.state = State.ALU_INDIRECT_MEM
        elif state == State.ALU_INDIRECT_MEM:
            self.state = State.ALU_EXEC
        elif state == State.ALU_EXEC:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.CMP_ADDR:
            self.state = State.CMP_MEM
        elif state == State.CMP_MEM:
            self.state = State.CMP_INDIRECT_ADDR if mode == AddressingMode.INDIRECT else State.CMP_EXEC
        elif state == State.CMP_INDIRECT_ADDR:
            self.state = State.CMP_INDIRECT_MEM
        elif state == State.CMP_INDIRECT_MEM:
            self.state = State.CMP_EXEC
        elif state == State.CMP_EXEC or state in {State.JUMP_EXEC, State.BRANCH_EXEC}:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.PUSH_DEC_SP:
            self.state = State.PUSH_WRITE_ADDR
        elif state == State.PUSH_WRITE_ADDR:
            self.state = State.PUSH_WRITE_DATA
        elif state == State.PUSH_WRITE_DATA:
            self.state = State.PUSH_MEM
        elif state == State.PUSH_MEM:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.POP_ADDR:
            self.state = State.POP_READ
        elif state == State.POP_READ:
            self.state = State.POP_WB
        elif state == State.POP_WB or state == State.DROP_INC_SP:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.CALL_DEC_SP:
            self.state = State.CALL_SAVE_PC
        elif state == State.CALL_SAVE_PC:
            self.state = State.CALL_WRITE
        elif state == State.CALL_WRITE:
            self.state = State.CALL_JUMP
        elif state == State.CALL_JUMP:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.RET_ADDR:
            self.state = State.RET_READ
        elif state == State.RET_READ:
            self.state = State.RET_JUMP
        elif state == State.RET_JUMP:
            self.state = State.RET_INC_SP
        elif state == State.RET_INC_SP:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.INT_SAVE_PC_DEC_SP:
            self.state = State.INT_SAVE_PC_WRITE
        elif state == State.INT_SAVE_PC_WRITE:
            self.state = State.INT_SAVE_PC_MEM
        elif state == State.INT_SAVE_PC_MEM:
            self.state = State.INT_SAVE_FLAGS_DEC_SP
        elif state == State.INT_SAVE_FLAGS_DEC_SP:
            self.state = State.INT_SAVE_FLAGS_WRITE
        elif state == State.INT_SAVE_FLAGS_WRITE:
            self.state = State.INT_SAVE_FLAGS_MEM
        elif state == State.INT_SAVE_FLAGS_MEM:
            self.state = State.INT_SAVE_ACC_DEC_SP
        elif state == State.INT_SAVE_ACC_DEC_SP:
            self.state = State.INT_SAVE_ACC_WRITE
        elif state == State.INT_SAVE_ACC_WRITE:
            self.state = State.INT_SAVE_ACC_MEM
        elif state == State.INT_SAVE_ACC_MEM:
            self.state = State.INT_JUMP_VECTOR
        elif state == State.INT_JUMP_VECTOR:
            self.state = State.FETCH_IR

        elif state == State.IRET_RESTORE_ACC_ADDR:
            self.state = State.IRET_RESTORE_ACC_READ
        elif state == State.IRET_RESTORE_ACC_READ:
            self.state = State.IRET_RESTORE_ACC_WB
        elif state == State.IRET_RESTORE_ACC_WB:
            self.state = State.IRET_RESTORE_FLAGS_ADDR
        elif state == State.IRET_RESTORE_FLAGS_ADDR:
            self.state = State.IRET_RESTORE_FLAGS_READ
        elif state == State.IRET_RESTORE_FLAGS_READ:
            self.state = State.IRET_RESTORE_FLAGS_WB
        elif state == State.IRET_RESTORE_FLAGS_WB:
            self.state = State.IRET_RESTORE_PC_ADDR
        elif state == State.IRET_RESTORE_PC_ADDR:
            self.state = State.IRET_RESTORE_PC_READ
        elif state == State.IRET_RESTORE_PC_READ:
            self.state = State.IRET_RESTORE_PC_WB
        elif state == State.IRET_RESTORE_PC_WB:
            self.state = self._after_instruction(interrupt_enter)

        elif state == State.HALT:
            self.state = State.HALT
        else:
            raise ProcessorError(f"unhandled CU state: {state.name}")

        return self.state

    def _after_instruction(self, interrupt_enter: bool) -> State:
        return State.INT_SAVE_PC_DEC_SP if interrupt_enter else State.FETCH_IR


class ControlSignalGenerator:
    def generate(self, state: State, instruction: Instruction, branch_taken: bool) -> ControlSignals:
        mode = instruction.mode
        opcode = instruction.opcode

        if state == State.FETCH_IR:
            return ControlSignals(imem_read=True, latch_ir=True)
        if state == State.FETCH_PC_INC:
            return ControlSignals(
                sel_pc_mux=PCMux.ALU_RESULT,
                sel_alu_a_mux=ALUAMux.PC,
                sel_alu_b_mux=ALUBMux.CONST_4,
                alu_op=ALUOp.ADD,
                latch_pc=True,
            )
        if state == State.DECODE:
            return ControlSignals()

        if state == State.LOAD_IMM:
            return ControlSignals(sel_acc_mux=ACCMux.IR_OPERAND, latch_acc=True)

        if state in ADDRESS_SETUP_STATES:
            return self._address_signals(mode)

        if state in READ_TO_DR_STATES:
            return ControlSignals(dmem_read=True, sel_dr_mux=DRMux.DMEM_DATA_OUT, latch_dr=True)

        if state in DR_TO_AR_STATES:
            return ControlSignals(sel_ar_mux=ARMux.DR, latch_ar=True)

        if state == State.LOAD_WB:
            return ControlSignals(sel_acc_mux=ACCMux.DR, latch_acc=True)

        if state == State.STORE_PREPARE:
            return ControlSignals(sel_dr_mux=DRMux.ACC, latch_dr=True)
        if state == State.STORE_MEM:
            return ControlSignals(dmem_write=True)

        if state == State.ALU_EXEC:
            return self._alu_exec_signals(opcode, mode, latch_acc=True)
        if state == State.CMP_EXEC:
            return self._alu_exec_signals(Opcode.SUB, mode, latch_acc=False)

        if state == State.JUMP_EXEC:
            return ControlSignals(sel_pc_mux=PCMux.IR_OPERAND, latch_pc=True)
        if state == State.BRANCH_EXEC:
            return ControlSignals(sel_pc_mux=PCMux.IR_OPERAND, latch_pc=branch_taken)

        if state == State.PUSH_DEC_SP:
            return self._sp_update_signals(ALUOp.SUB)
        if state == State.PUSH_WRITE_ADDR:
            return ControlSignals(sel_ar_mux=ARMux.SP, latch_ar=True)
        if state == State.PUSH_WRITE_DATA:
            return ControlSignals(sel_dr_mux=DRMux.ACC, latch_dr=True)
        if state == State.PUSH_MEM:
            return ControlSignals(dmem_write=True)

        if state == State.POP_ADDR:
            return ControlSignals(sel_ar_mux=ARMux.SP, latch_ar=True, check_stack_pop=True)
        if state == State.POP_READ:
            return ControlSignals(dmem_read=True, sel_dr_mux=DRMux.DMEM_DATA_OUT, latch_dr=True)
        if state == State.POP_WB:
            return ControlSignals(
                sel_acc_mux=ACCMux.DR,
                latch_acc=True,
                sel_alu_a_mux=ALUAMux.SP,
                sel_alu_b_mux=ALUBMux.CONST_4,
                alu_op=ALUOp.ADD,
                latch_sp=True,
            )

        if state == State.DROP_INC_SP:
            signals = self._sp_update_signals(ALUOp.ADD)
            signals.check_stack_pop = True
            return signals

        if state == State.CALL_DEC_SP:
            return self._sp_update_signals(ALUOp.SUB)
        if state == State.CALL_SAVE_PC:
            return ControlSignals(sel_ar_mux=ARMux.SP, latch_ar=True, sel_dr_mux=DRMux.PC, latch_dr=True)
        if state == State.CALL_WRITE:
            return ControlSignals(dmem_write=True)
        if state == State.CALL_JUMP:
            return ControlSignals(sel_pc_mux=PCMux.IR_OPERAND, latch_pc=True)

        if state == State.RET_ADDR:
            return ControlSignals(sel_ar_mux=ARMux.SP, latch_ar=True, check_stack_pop=True)
        if state == State.RET_READ:
            return ControlSignals(dmem_read=True, sel_dr_mux=DRMux.DMEM_DATA_OUT, latch_dr=True)
        if state == State.RET_JUMP:
            return ControlSignals(sel_pc_mux=PCMux.DR, latch_pc=True)
        if state == State.RET_INC_SP:
            return self._sp_update_signals(ALUOp.ADD)

        if state == State.INT_SAVE_PC_DEC_SP:
            signals = self._sp_update_signals(ALUOp.SUB)
            signals.set_in_isr = True
            signals.clear_irq_pending = True
            return signals
        if state == State.INT_SAVE_PC_WRITE:
            return ControlSignals(sel_ar_mux=ARMux.SP, latch_ar=True, sel_dr_mux=DRMux.PC, latch_dr=True)
        if state == State.INT_SAVE_PC_MEM:
            return ControlSignals(dmem_write=True)
        if state == State.INT_SAVE_FLAGS_DEC_SP:
            return self._sp_update_signals(ALUOp.SUB)
        if state == State.INT_SAVE_FLAGS_WRITE:
            return ControlSignals(sel_ar_mux=ARMux.SP, latch_ar=True, sel_dr_mux=DRMux.FLAGS, latch_dr=True)
        if state == State.INT_SAVE_FLAGS_MEM:
            return ControlSignals(dmem_write=True)
        if state == State.INT_SAVE_ACC_DEC_SP:
            return self._sp_update_signals(ALUOp.SUB)
        if state == State.INT_SAVE_ACC_WRITE:
            return ControlSignals(sel_ar_mux=ARMux.SP, latch_ar=True, sel_dr_mux=DRMux.ACC, latch_dr=True)
        if state == State.INT_SAVE_ACC_MEM:
            return ControlSignals(dmem_write=True)
        if state == State.INT_JUMP_VECTOR:
            return ControlSignals(sel_pc_mux=PCMux.INT_VECTOR, latch_pc=True)

        if state in IRET_ADDR_STATES:
            return ControlSignals(sel_ar_mux=ARMux.SP, latch_ar=True, check_stack_pop=True)

        if state in IRET_READ_STATES:
            return ControlSignals(dmem_read=True, sel_dr_mux=DRMux.DMEM_DATA_OUT, latch_dr=True)

        if state == State.IRET_RESTORE_ACC_WB:
            signals = self._sp_update_signals(ALUOp.ADD)
            signals.sel_acc_mux = ACCMux.DR
            signals.latch_acc = True
            return signals
        if state == State.IRET_RESTORE_FLAGS_WB:
            signals = self._sp_update_signals(ALUOp.ADD)
            signals.sel_flags_mux = FlagsMux.DR
            signals.latch_flags = True
            return signals
        if state == State.IRET_RESTORE_PC_WB:
            signals = self._sp_update_signals(ALUOp.ADD)
            signals.sel_pc_mux = PCMux.DR
            signals.latch_pc = True
            signals.clear_in_isr = True
            return signals

        if state == State.HALT:
            return ControlSignals()

        raise ProcessorError(f"cannot generate signals for state: {state.name}")

    def _address_signals(self, mode: AddressingMode) -> ControlSignals:
        if mode == AddressingMode.STACK_RELATIVE:
            return ControlSignals(
                sel_ar_mux=ARMux.ALU_RESULT,
                sel_alu_a_mux=ALUAMux.SP,
                sel_alu_b_mux=ALUBMux.IR_OPERAND,
                alu_op=ALUOp.ADD,
                latch_ar=True,
            )
        return ControlSignals(sel_ar_mux=ARMux.IR_OPERAND, latch_ar=True)

    def _alu_exec_signals(self, opcode: Opcode, mode: AddressingMode, latch_acc: bool) -> ControlSignals:
        alu_op = {
            Opcode.ADD: ALUOp.ADD,
            Opcode.SUB: ALUOp.SUB,
            Opcode.MUL: ALUOp.MUL,
            Opcode.DIV: ALUOp.DIV,
            Opcode.MOD: ALUOp.MOD,
        }.get(opcode, ALUOp.SUB)
        return ControlSignals(
            sel_acc_mux=ACCMux.ALU_RESULT,
            latch_acc=latch_acc,
            sel_flags_mux=FlagsMux.ALU_NZVC,
            latch_flags=True,
            sel_alu_a_mux=ALUAMux.ACC,
            sel_alu_b_mux=ALUBMux.IR_OPERAND if mode == AddressingMode.IMMEDIATE else ALUBMux.DR,
            alu_op=alu_op,
        )

    def _sp_update_signals(self, op: ALUOp) -> ControlSignals:
        return ControlSignals(
            sel_alu_a_mux=ALUAMux.SP,
            sel_alu_b_mux=ALUBMux.CONST_4,
            alu_op=op,
            latch_sp=True,
        )


class ControlUnit:
    def __init__(self, datapath: DataPath) -> None:
        self.datapath = datapath
        self.instruction_decoder = InstructionDecoder()
        self.branch_logic = BranchLogic()
        self.interrupt_controller = InterruptController()
        self.fsm = ControlSequencer()
        self.control_signal_generator = ControlSignalGenerator()

    @property
    def state(self) -> State:
        return self.fsm.state

    @state.setter
    def state(self, value: State) -> None:
        self.fsm.state = value

    @property
    def IN_ISR(self) -> bool:
        return self.interrupt_controller.in_isr

    @property
    def IRQ_PENDING(self) -> bool:
        return self.interrupt_controller.irq_pending

    def decode_instruction(self) -> State:
        return self.instruction_decoder.decode(self.datapath.IR)

    def evaluate_branch(self) -> bool:
        return self.branch_logic.evaluate(self.datapath.IR, self.datapath.FLAGS)

    def evaluate_interrupt(self) -> bool:
        return self.interrupt_controller.evaluate()

    def request_interrupt(self) -> None:
        self.interrupt_controller.request_interrupt()

    def next_state(self) -> State:
        decoded_state = self.decode_instruction() if self.state == State.DECODE else self.state
        return self.fsm.next_state(self.datapath.IR.mode, decoded_state, self.evaluate_interrupt())

    def generate_control_signals(self) -> ControlSignals:
        return self.control_signal_generator.generate(self.state, self.datapath.IR, self.evaluate_branch())

    def apply_control_signals(self, signals: ControlSignals) -> None:
        self.interrupt_controller.apply_control_signals(signals)
