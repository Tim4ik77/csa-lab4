from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ASTError(ValueError):
    """Raised when parsed forms are structurally invalid."""


@dataclass(frozen=True)
class Literal:
    kind: str
    value: int | str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "literal", "kind": self.kind, "value": self.value}


@dataclass(frozen=True)
class Symbol:
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "symbol", "name": self.name}


@dataclass(frozen=True)
class Begin:
    expressions: list[Expr]

    def to_dict(self) -> dict[str, Any]:
        return {"type": "begin", "expressions": [expr.to_dict() for expr in self.expressions]}


@dataclass(frozen=True)
class Setq:
    name: str
    expression: Expr

    def to_dict(self) -> dict[str, Any]:
        return {"type": "setq", "name": self.name, "expression": self.expression.to_dict()}


@dataclass(frozen=True)
class If:
    condition: Expr
    then_branch: Expr
    else_branch: Expr

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "if",
            "condition": self.condition.to_dict(),
            "then": self.then_branch.to_dict(),
            "else": self.else_branch.to_dict(),
        }


@dataclass(frozen=True)
class While:
    condition: Expr
    body: list[Expr]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "while",
            "condition": self.condition.to_dict(),
            "body": [expr.to_dict() for expr in self.body],
        }


@dataclass(frozen=True)
class BinaryOp:
    operator: str
    left: Expr
    right: Expr

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "binary",
            "operator": self.operator,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }


@dataclass(frozen=True)
class Compare:
    operator: str
    left: Expr
    right: Expr

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "compare",
            "operator": self.operator,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }


@dataclass(frozen=True)
class MemGet:
    address: Expr

    def to_dict(self) -> dict[str, Any]:
        return {"type": "mem-get", "address": self.address.to_dict()}


@dataclass(frozen=True)
class MemSet:
    address: Expr
    value: Expr

    def to_dict(self) -> dict[str, Any]:
        return {"type": "mem-set", "address": self.address.to_dict(), "value": self.value.to_dict()}


@dataclass(frozen=True)
class Call:
    name: str
    arguments: list[Expr]

    def to_dict(self) -> dict[str, Any]:
        return {"type": "call", "name": self.name, "arguments": [arg.to_dict() for arg in self.arguments]}


Expr = Literal | Symbol | Begin | Setq | If | While | BinaryOp | Compare | MemGet | MemSet | Call


@dataclass(frozen=True)
class DefConst:
    name: str
    value: Literal

    def to_dict(self) -> dict[str, Any]:
        return {"type": "defconst", "name": self.name, "value": self.value.to_dict()}


@dataclass(frozen=True)
class DefVar:
    name: str
    value: Literal

    def to_dict(self) -> dict[str, Any]:
        return {"type": "defvar", "name": self.name, "value": self.value.to_dict()}


@dataclass(frozen=True)
class DefBuffer:
    name: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"type": "defbuffer", "name": self.name, "size": self.size}


@dataclass(frozen=True)
class Defun:
    name: str
    parameters: list[str]
    body: list[Expr]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "defun",
            "name": self.name,
            "parameters": self.parameters,
            "body": [expr.to_dict() for expr in self.body],
        }


@dataclass(frozen=True)
class OnInput:
    body: list[Expr]

    def to_dict(self) -> dict[str, Any]:
        return {"type": "on-input", "body": [expr.to_dict() for expr in self.body]}


TopLevel = DefConst | DefVar | DefBuffer | Defun | OnInput


@dataclass(frozen=True)
class Program:
    forms: list[TopLevel] = field(default_factory=list)

    def functions(self) -> dict[str, Defun]:
        return {form.name: form for form in self.forms if isinstance(form, Defun)}

    def on_input(self) -> OnInput | None:
        handlers = [form for form in self.forms if isinstance(form, OnInput)]
        if len(handlers) > 1:
            raise ASTError("only one on-input form is allowed")
        return handlers[0] if handlers else None

    def to_dict(self) -> dict[str, Any]:
        return {"type": "program", "forms": [form.to_dict() for form in self.forms]}
