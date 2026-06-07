from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from . import ast


class ParserError(ValueError):
    """Raised when source code cannot be parsed."""


TokenValue = str | int | tuple[str, str]


def _decode_escape(char: str) -> str:
    escapes = {"n": "\n", "t": "\t", "0": "\0", "\\": "\\", "'": "'", '"': '"'}
    if char not in escapes:
        raise ParserError(f"unknown escape sequence: \\{char}")
    return escapes[char]


def tokenize(source: str) -> list[TokenValue]:
    tokens: list[TokenValue] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            while index < len(source) and source[index] != "\n":
                index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            chars: list[str] = []
            while index < len(source):
                current = source[index]
                if current == '"':
                    index += 1
                    tokens.append(("string", "".join(chars)))  # type: ignore[arg-type]
                    break
                if current == "\\":
                    index += 1
                    if index >= len(source):
                        raise ParserError("unterminated string escape")
                    chars.append(_decode_escape(source[index]))
                    index += 1
                    continue
                if current == "\n":
                    raise ParserError("newline in string literal")
                chars.append(current)
                index += 1
            else:
                raise ParserError("unterminated string literal")
            continue
        if char == "'":
            index += 1
            if index >= len(source):
                raise ParserError("unterminated char literal")
            if source[index] == "\\":
                index += 1
                if index >= len(source):
                    raise ParserError("unterminated char escape")
                value = _decode_escape(source[index])
                index += 1
            else:
                value = source[index]
                index += 1
            if index >= len(source) or source[index] != "'":
                raise ParserError("char literal must contain one character")
            index += 1
            tokens.append(("char", value))  # type: ignore[arg-type]
            continue

        start = index
        while index < len(source) and not source[index].isspace() and source[index] not in "();":
            index += 1
        token = source[start:index]
        if re.fullmatch(r"-?\d+", token):
            tokens.append(int(token))
        else:
            tokens.append(token)
    return tokens


class _Parser:
    def __init__(self, tokens: list[Any]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Any:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def pop(self) -> Any:
        token = self.peek()
        if token is None:
            raise ParserError("unexpected end of file")
        self.pos += 1
        return token

    def expect(self, expected: str) -> None:
        token = self.pop()
        if token != expected:
            raise ParserError(f"expected {expected!r}, got {token!r}")

    def parse_program(self) -> ast.Program:
        forms: list[ast.TopLevel] = []
        while self.peek() is not None:
            forms.append(self.parse_top_level())
        return ast.Program(forms)

    def parse_top_level(self) -> ast.TopLevel:
        self.expect("(")
        head = self.pop()
        if head == "defconst":
            name = self.parse_symbol_name()
            value = self.parse_literal()
            self.expect(")")
            return ast.DefConst(name, value)
        if head == "defvar":
            name = self.parse_symbol_name()
            value = self.parse_literal()
            self.expect(")")
            return ast.DefVar(name, value)
        if head == "defbuffer":
            name = self.parse_symbol_name()
            size = self.pop()
            if not isinstance(size, int) or size < 0:
                raise ParserError("defbuffer size must be a non-negative integer")
            self.expect(")")
            return ast.DefBuffer(name, size)
        if head == "defun":
            name = self.parse_symbol_name()
            self.expect("(")
            params: list[str] = []
            while self.peek() != ")":
                params.append(self.parse_symbol_name())
            self.expect(")")
            function_body: list[ast.Expr] = []
            while self.peek() != ")":
                function_body.append(self.parse_expr())
            self.expect(")")
            if not function_body:
                raise ParserError("function body cannot be empty")
            return ast.Defun(name, params, function_body)
        if head == "on-input":
            handler_body: list[ast.Expr] = []
            while self.peek() != ")":
                handler_body.append(self.parse_expr())
            self.expect(")")
            if not handler_body:
                raise ParserError("on-input body cannot be empty")
            return ast.OnInput(handler_body)
        raise ParserError(f"unknown top-level form: {head!r}")

    def parse_expr(self) -> ast.Expr:
        token = self.peek()
        if token == "(":
            return self.parse_list_expr()
        if isinstance(token, (int, tuple)):
            return self.parse_literal()
        return ast.Symbol(self.parse_symbol_name())

    def parse_list_expr(self) -> ast.Expr:
        self.expect("(")
        head = self.pop()
        if head == "begin":
            expressions = self.parse_until_close()
            if not expressions:
                raise ParserError("begin requires at least one expression")
            return ast.Begin(expressions)
        if head == "setq":
            name = self.parse_symbol_name()
            expression = self.parse_expr()
            self.expect(")")
            return ast.Setq(name, expression)
        if head == "if":
            condition = self.parse_expr()
            then_branch = self.parse_expr()
            else_branch = self.parse_expr()
            self.expect(")")
            return ast.If(condition, then_branch, else_branch)
        if head == "while":
            condition = self.parse_expr()
            body = self.parse_until_close()
            if not body:
                raise ParserError("while requires at least one body expression")
            return ast.While(condition, body)
        if head in {"+", "-", "*", "/", "mod"}:
            left = self.parse_expr()
            right = self.parse_expr()
            self.expect(")")
            return ast.BinaryOp(head, left, right)
        if head in {"=", "!=", "<", "<=", ">", ">="}:
            left = self.parse_expr()
            right = self.parse_expr()
            self.expect(")")
            return ast.Compare(head, left, right)
        if head == "mem-get":
            address = self.parse_expr()
            self.expect(")")
            return ast.MemGet(address)
        if head == "mem-set":
            address = self.parse_expr()
            value = self.parse_expr()
            self.expect(")")
            return ast.MemSet(address, value)
        if not isinstance(head, str):
            raise ParserError(f"invalid call head: {head!r}")
        args = self.parse_until_close()
        return ast.Call(head, args)

    def parse_until_close(self) -> list[ast.Expr]:
        expressions: list[ast.Expr] = []
        while self.peek() != ")":
            if self.peek() is None:
                raise ParserError("missing closing parenthesis")
            expressions.append(self.parse_expr())
        self.expect(")")
        return expressions

    def parse_literal(self) -> ast.Literal:
        token = self.pop()
        if isinstance(token, int):
            return ast.Literal("integer", token)
        if isinstance(token, tuple) and len(token) == 2:
            kind, value = token
            if kind == "char":
                if len(value) != 1:
                    raise ParserError("char literal must decode to one character")
                return ast.Literal("char", ord(value))
            if kind == "string":
                return ast.Literal("string", value)
        raise ParserError(f"expected literal, got {token!r}")

    def parse_symbol_name(self) -> str:
        token = self.pop()
        if not isinstance(token, str) or token in {"(", ")"}:
            raise ParserError(f"expected symbol, got {token!r}")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_?!-]*", token):
            raise ParserError(f"invalid symbol: {token!r}")
        return token


def parse(source: str) -> ast.Program:
    parser = _Parser(tokenize(source))
    return parser.parse_program()


def parse_file(path: str | Path) -> ast.Program:
    return parse(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("source")
    args = cli.parse_args(argv)
    program = parse_file(args.source)
    print(json.dumps(program.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
