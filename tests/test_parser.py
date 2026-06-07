import pytest

from src import ast
from src.parser import ParserError, parse


def test_parse_top_level_forms_and_nested_expressions():
    program = parse(
        """
        (defconst A 1)
        (defvar x 0)
        (defbuffer BUF 4)
        (defun main () (begin (setq x (+ A 2)) (if (> x 1) x 0)))
        (on-input (mem-set 8 (mem-get 0)))
        """
    )

    assert len(program.forms) == 5
    assert isinstance(program.forms[0], ast.DefConst)
    main = program.functions()["main"]
    assert isinstance(main.body[0], ast.Begin)
    assert isinstance(main.body[0].expressions[0], ast.Setq)
    assert isinstance(main.body[0].expressions[1], ast.If)


def test_parse_strings_chars_and_escapes():
    program = parse(r"""
    (defconst NL '\n')
    (defconst TEXT "A\tB\n")
    (defun main () TEXT)
    """)

    consts = [form for form in program.forms if isinstance(form, ast.DefConst)]
    assert consts[0].value.value == ord("\n")
    assert consts[1].value.value == "A\tB\n"


def test_parser_rejects_invalid_symbol():
    with pytest.raises(ParserError):
        parse("(defun 1bad () 0)")
