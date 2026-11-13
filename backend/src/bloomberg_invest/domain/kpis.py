"""The KPI rules and how a KPI value is computed (#7, #19 R10, R12, R14; #27). Loaded from the
versioned configuration in `bloomberg_invest/config/kpis/`.

A KPI's formula is configuration, read by a small evaluator here: numbers, input names,
`+ - * /`, comparisons, and `prev(x)` (x one fiscal year earlier), `avg(x)` (the average of x
and prev(x): opening and closing balances), `abs(x)`. Everything else is refused when the rules
load. The same text computes the value and documents it on the KPIs page, so they never drift.
"""

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from enum import StrEnum
from typing import Literal

from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.model import RunInfo

Format = Literal["percent", "multiple", "amount", "score"]
Applies = Literal["all", "non_financial"]
Measure = Literal["per_share", "total"]
MEASURES: tuple[Measure, ...] = ("per_share", "total")
FUNCTIONS = ("prev", "avg", "abs")
EXACT = Decimal("1e-9")  # a computed value is kept to nine decimals


@dataclass(frozen=True)
class Input:
    """A financial figure a KPI reads: a line item, or one breakdown of it."""

    line_item: str
    breakdown: str = ""  # empty for the line item itself


@dataclass(frozen=True)
class Declared:
    """The dividend a company declares for the fiscal year: a dividend Fact (#53), not a figure."""

    measure: Measure


Source = Input | Declared


@dataclass(frozen=True)
class Formula:
    """A formula as configuration writes it, parsed and checked."""

    text: str
    tree: ast.expr = field(compare=False, repr=False)

    @classmethod
    def parse(cls, text: str) -> "Formula":
        text = " ".join(text.split())  # a long formula may wrap over lines
        try:
            tree = ast.parse(text, mode="eval").body
        except SyntaxError as error:
            raise ValueError(f"formula {text!r} can't be read: {error.msg}") from None
        _check(tree, text)
        return cls(text, tree)

    @property
    def names(self) -> tuple[str, ...]:
        """The input names it reads, in the order it first writes them."""
        found = [n for n in ast.walk(self.tree) if isinstance(n, ast.Name)]
        ordered = sorted(found, key=lambda n: n.col_offset)
        return tuple(dict.fromkeys(n.id for n in ordered if n.id not in FUNCTIONS))

    def render(self, titles: Mapping[str, str]) -> str:
        """The formula as a person reads it: input titles, `x FY-1`, `average x`. An expense
        is read as a positive amount, so `abs` is left out."""
        return _render(self.tree, titles, 0)


def _check(node: ast.expr, text: str) -> None:
    def refuse(why: str) -> ValueError:
        return ValueError(f"formula {text!r}: {why}")

    match node:
        case ast.Constant(value=int() | float()):
            pass
        case ast.Name():
            if node.id in FUNCTIONS:
                raise refuse(f"{node.id} is a function")
        case ast.BinOp(op=ast.Add() | ast.Sub() | ast.Mult() | ast.Div()):
            _check(node.left, text)
            _check(node.right, text)
        case ast.UnaryOp(op=ast.USub()):
            _check(node.operand, text)
        case ast.Compare(ops=[ast.Gt() | ast.Lt() | ast.GtE() | ast.LtE()], comparators=[right]):
            _check(node.left, text)
            _check(right, text)
        case ast.Call(func=ast.Name(id=name), args=[arg], keywords=[]) if name in FUNCTIONS:
            _check(arg, text)
        case _:
            raise refuse(f"{ast.unparse(node)!r} is not allowed")


_OPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "×", ast.Div: "/"}
_COMPARE = {ast.Gt: ">", ast.Lt: "<", ast.GtE: "≥", ast.LtE: "≤"}
_PRECEDENCE = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2}


def _render(node: ast.expr, titles: Mapping[str, str], outer: int) -> str:
    match node:
        case ast.Constant(value=value):
            return str(value)
        case ast.Name(id=name):
            # Inside a formula a title reads as words: "net income group share", but "EBITDA".
            title = titles.get(name, name).replace(", ", " ")
            return title[0].lower() + title[1:] if title[1:2].islower() else title
        case ast.UnaryOp(operand=operand):
            return "-" + _render(operand, titles, 3)
        case ast.BinOp(left=left, op=op, right=right):
            level = _PRECEDENCE[type(op)]
            # The right side of - and / binds tighter: a - (b - c), a / (b × c).
            text = (
                f"{_render(left, titles, level)} {_OPS[type(op)]} "
                f"{_render(right, titles, level + (1 if isinstance(op, ast.Sub | ast.Div) else 0))}"
            )
            return f"({text})" if level < outer else text
        case ast.Compare(left=left, ops=[op], comparators=[right]):
            return f"{_render(left, titles, 0)} {_COMPARE[type(op)]} {_render(right, titles, 0)}"
        case ast.Call(func=ast.Name(id="abs"), args=[arg]):
            return _render(arg, titles, outer)
        case ast.Call(func=ast.Name(id="prev"), args=[ast.Name() as arg]):
            return f"{_render(arg, titles, 3)} FY-1"
        case ast.Call(func=ast.Name(id="prev"), args=[arg]):
            return f"({_render(arg, titles, 0)}) FY-1"
        case ast.Call(func=ast.Name(id="avg"), args=[arg]):
            inner = _render(arg, titles, 3 if isinstance(arg, ast.Name) else 0)
            return f"average {inner}" if isinstance(arg, ast.Name) else f"average ({inner})"
    raise ValueError(f"can't render {ast.unparse(node)!r}")


@dataclass(frozen=True)
class Test:
    """One pass/fail test of a composite score (the Piotroski F-score)."""

    __test__ = False  # not a pytest class

    name: str
    title: str
    formula: Formula


@dataclass(frozen=True)
class Kpi:
    name: str
    title: str
    inputs: tuple[Input, ...]  # the figures it reads, which need a check (#19 R10)
    theme: str = ""
    means: str = ""  # what it means, for the KPIs page
    read: str = ""  # how to read it
    format: Format = "percent"
    band: tuple[Decimal, Decimal] | None = None  # the rule-of-thumb band, in its format's unit
    applies: Applies = "all"
    formula: Formula | None = None  # None until its ticket computes it (#28, #29)
    when: Formula | None = None  # computed only when this holds, else not meaningful
    tests: tuple[Test, ...] = ()  # a score's tests: its value is how many pass

    @property
    def computed(self) -> bool:
        return self.formula is not None or bool(self.tests)

    @property
    def formulas(self) -> tuple[Formula, ...]:
        return tuple(
            f for f in (self.formula, self.when, *(t.formula for t in self.tests)) if f is not None
        )


@dataclass(frozen=True)
class KpiRules:
    version: str
    sha256: str  # of the configuration file
    kpis: tuple[Kpi, ...]
    since: date | None = None  # when this version came into force
    financial_sectors: tuple[str, ...] = ()  # Listing sectors of banks and insurers
    sources: Mapping[str, Source] = field(default_factory=dict)  # names that are no line item
    # Names no filing of the kind reports, and why: what reads them is not meaningful.
    not_reported: Mapping[str, str] = field(default_factory=dict)
    titles: Mapping[str, str] = field(default_factory=dict)  # each name's title, for people
    themes: Mapping[str, str] = field(default_factory=dict)  # each theme's title, in page order

    def feeds(self, line_item: str, breakdown: str) -> list[str]:
        """The titles of the KPIs and screens that read this line item and breakdown."""
        wanted = Input(line_item, breakdown)
        return [kpi.title for kpi in self.kpis if wanted in kpi.inputs]

    def financial(self, sector: str | None) -> bool:
        """A bank or insurer, from its Listing's sector (#7)."""
        return sector is not None and sector in self.financial_sectors

    def declared_feeds(self, measure: Measure) -> list[str]:
        """The titles of the KPIs that read the declared dividend in this measure."""
        wanted = Declared(measure)
        return [
            kpi.title
            for kpi in self.kpis
            if any(self.source(n) == wanted for f in kpi.formulas for n in f.names)
        ]

    def source(self, name: str) -> Source | None:
        """What a formula's name reads: a figure, a declared dividend, or None when it is not
        reported."""
        if name in self.not_reported:
            return None
        return self.sources.get(name, Input(name))

    def check_against(self, label_map: LabelMap) -> None:
        """Fail when an input names a line item the label map does not have, or a formula
        names something that is neither a line item nor a source the rules define."""
        for kpi in self.kpis:
            if kpi.theme and kpi.theme not in self.themes:
                raise ValueError(f"KPI {kpi.name!r} has theme {kpi.theme!r}, which has no title")
            for i in kpi.inputs:
                if i.line_item not in label_map.items:
                    raise ValueError(
                        f"KPI {kpi.name!r} reads {i.line_item!r}, which label map "
                        f"{label_map.version} does not have"
                    )
            for formula in kpi.formulas:
                for name in formula.names:
                    source = self.source(name)
                    if isinstance(source, Input) and source.line_item not in label_map.items:
                        raise ValueError(
                            f"KPI {kpi.name!r} reads {name!r}, which label map "
                            f"{label_map.version} does not have"
                        )


def inputs_of(formulas: tuple[Formula, ...], rules: KpiRules) -> tuple[Input, ...]:
    """The figures some formulas read, in the order they first name them."""
    found = (rules.source(name) for formula in formulas for name in formula.names)
    return tuple(dict.fromkeys(s for s in found if isinstance(s, Input)))


# ---- Computing


class KpiStatus(StrEnum):
    """Where a KPI value stands: computed, or why it is not (#19 R10, R12)."""

    computed = "computed"
    not_meaningful = "not_meaningful"  # a bank or insurer, or a formula that can't apply
    missing = "missing"  # an input is not extracted or not found
    conflict = "conflict"  # filings state an input with different values
    unchecked = "unchecked"  # an input waits for a person's check


# The status a KPI takes when its inputs have several problems: the first that applies.
_WORST = (KpiStatus.missing, KpiStatus.conflict, KpiStatus.unchecked)


@dataclass(frozen=True)
class InputValue:
    """An input's value in force for one fiscal year: one value, or several when filings state
    it differently; checked once a person checked it; with the Facts that state it."""

    values: tuple[Decimal, ...]
    checked: bool
    ids: tuple[str, ...]


# What the computation is given: each (name, fiscal year) an input has a value for.
Inputs = Mapping[tuple[str, int], InputValue]


@dataclass(frozen=True)
class Used:
    """An input a value read, for one fiscal year."""

    name: str
    fiscal_year: int


@dataclass(frozen=True)
class TestResult:
    __test__ = False  # not a pytest class

    name: str
    status: KpiStatus
    passed: bool | None  # None until it is computed
    reason: str


@dataclass(frozen=True)
class KpiResult:
    kpi: str
    fiscal_year: int
    status: KpiStatus
    value: Decimal | None  # for a score, how many tests pass
    reason: str  # why there is no value; empty when computed
    used: tuple[Used, ...]  # every input it reads, for the hover
    sources: tuple[str, ...]  # the Facts it was computed from
    tests: tuple[TestResult, ...] = ()
    out_of: int | None = None  # for a score, the tests it counts: those that are meaningful


@dataclass(frozen=True)
class KpiChange:
    """The KPI values of one issuer a recompute writes, in its compute Run: the results that
    changed, and the (KPI, fiscal year) values no longer computed."""

    isin: str
    results: tuple[KpiResult, ...]
    gone: tuple[tuple[str, int], ...]
    run: RunInfo
    rule_version: str
    rule_sha256: str
    label_map: str  # the version the figures were read with
    superseded: int  # the current values it replaces: of the results, and gone


class _NotMeaningful(Exception):
    """A division by zero: its argument is the divisor's expression."""


def compute(rules: KpiRules, inputs: Inputs, fiscal_year: int, financial: bool) -> list[KpiResult]:
    """Every computed KPI of one company for one fiscal year. Nothing is computed from a
    missing, disagreeing or unchecked input, and nothing is imputed (#7)."""
    return [_kpi(k, rules, inputs, fiscal_year, financial) for k in rules.kpis if k.computed]


def _kpi(kpi: Kpi, rules: KpiRules, inputs: Inputs, year: int, financial: bool) -> KpiResult:
    if financial and kpi.applies == "non_financial":
        return KpiResult(
            kpi.name,
            year,
            KpiStatus.not_meaningful,
            None,
            "Not meaningful for banks and insurers",
            (),
            (),
        )
    if kpi.tests:
        return _score(kpi, rules, inputs, year)
    assert kpi.formula is not None
    status, value, reason, used = _evaluate(kpi.formula, kpi.when, rules, inputs, year)
    return KpiResult(kpi.name, year, status, value, reason, used, _ids(used, inputs))


def _score(kpi: Kpi, rules: KpiRules, inputs: Inputs, year: int) -> KpiResult:
    results, used_all = [], []
    for test in kpi.tests:
        status, value, reason, used = _evaluate(test.formula, None, rules, inputs, year)
        used_all.extend(used)
        passed = None if value is None else value == 1
        results.append(TestResult(test.name, status, passed, reason))
    used = tuple(dict.fromkeys(used_all))
    # A test that can't apply to the company is left out: the score counts the others (#27).
    counted = [r for r in results if r.status != KpiStatus.not_meaningful]
    if not counted:
        reason = "Not meaningful: no test applies"
        return KpiResult(
            kpi.name, year, KpiStatus.not_meaningful, None, reason, used, (), tuple(results)
        )
    waiting = [r for r in counted if r.status != KpiStatus.computed]
    if not waiting:
        score = Decimal(sum(1 for r in counted if r.passed))
        return KpiResult(
            kpi.name,
            year,
            KpiStatus.computed,
            score,
            "",
            used,
            _ids(used, inputs),
            tuple(results),
            len(counted),
        )
    status = next(s for s in _WORST if any(r.status == s for r in waiting))
    reason = f"No score until all {len(counted)} tests have checked inputs: {len(waiting)} wait"
    return KpiResult(
        kpi.name, year, status, None, reason, used, _ids(used, inputs), tuple(results), len(counted)
    )


def _evaluate(
    formula: Formula, when: Formula | None, rules: KpiRules, inputs: Inputs, year: int
) -> tuple[KpiStatus, Decimal | None, str, tuple[Used, ...]]:
    """A formula's status, value, reason and the inputs it reads, for one fiscal year."""
    used = tuple(
        dict.fromkeys(_needs(formula.tree, year) + (_needs(when.tree, year) if when else ()))
    )
    not_reported = [
        rules.not_reported[n]
        for n in dict.fromkeys(u.name for u in used)
        if n in rules.not_reported
    ]
    if not_reported:
        return KpiStatus.not_meaningful, None, f"Not meaningful: {'; '.join(not_reported)}", used
    problems: dict[KpiStatus, list[str]] = {s: [] for s in _WORST}
    for u in used:
        title = f"{rules.titles.get(u.name, u.name)} FY{u.fiscal_year}"
        found = inputs.get((u.name, u.fiscal_year))
        if found is None:
            problems[KpiStatus.missing].append(title)
        elif len(found.values) > 1:
            problems[KpiStatus.conflict].append(title)
        elif not found.checked:
            problems[KpiStatus.unchecked].append(title)
    found = [s for s in _WORST if problems[s]]
    if found:
        # Every problem is named, worst first, so one look tells what is left to do.
        reason = "; ".join(f"{_SAYS[s]}: {', '.join(problems[s])}" for s in found)
        return found[0], None, reason, used

    def value(name: str, at: int) -> Decimal:
        return inputs[(name, at)].values[0]

    try:
        if when is not None and _eval(when.tree, year, value) != 1:
            return (
                KpiStatus.not_meaningful,
                None,
                f"Not meaningful unless {when.render(rules.titles)}",
                used,
            )
        result = _eval(formula.tree, year, value)
    except _NotMeaningful as error:
        zero = _render(error.args[0], rules.titles, 0)
        return KpiStatus.not_meaningful, None, f"Not meaningful: {zero} is zero", used
    return KpiStatus.computed, result.quantize(EXACT), "", used


_SAYS = {
    KpiStatus.missing: "Missing",
    KpiStatus.conflict: "Two values for",
    KpiStatus.unchecked: "Waiting for check",
}


def _needs(node: ast.expr, year: int) -> tuple[Used, ...]:
    """The inputs a formula reads at a fiscal year, `prev` and `avg` reaching back."""
    match node:
        case ast.Name(id=name):
            return (Used(name, year),)
        case ast.Constant():
            return ()
        case ast.Call(func=ast.Name(id="prev"), args=[arg]):
            return _needs(arg, year - 1)
        case ast.Call(func=ast.Name(id="avg"), args=[arg]):
            return _needs(arg, year) + _needs(arg, year - 1)
        case ast.Call(args=[arg]):
            return _needs(arg, year)
        case ast.BinOp(left=left, right=right):
            return _needs(left, year) + _needs(right, year)
        case ast.UnaryOp(operand=operand):
            return _needs(operand, year)
        case ast.Compare(left=left, comparators=[right]):
            return _needs(left, year) + _needs(right, year)
    raise ValueError(f"can't read {ast.unparse(node)!r}")


def _eval(node: ast.expr, year: int, value: Callable[[str, int], Decimal]) -> Decimal:
    """Exact decimal arithmetic; a comparison is 1 or 0."""
    with localcontext() as ctx:
        ctx.traps[DivisionByZero] = True
        ctx.traps[InvalidOperation] = True
        match node:
            case ast.Constant(value=v):
                return Decimal(str(v))
            case ast.Name(id=name):
                return value(name, year)
            case ast.Call(func=ast.Name(id="prev"), args=[arg]):
                return _eval(arg, year - 1, value)
            case ast.Call(func=ast.Name(id="avg"), args=[arg]):
                return (_eval(arg, year, value) + _eval(arg, year - 1, value)) / 2
            case ast.Call(func=ast.Name(id="abs"), args=[arg]):
                return abs(_eval(arg, year, value))
            case ast.UnaryOp(operand=operand):
                return -_eval(operand, year, value)
            case ast.BinOp(left=left, op=op, right=right):
                a, b = _eval(left, year, value), _eval(right, year, value)
                match op:
                    case ast.Add():
                        return a + b
                    case ast.Sub():
                        return a - b
                    case ast.Mult():
                        return a * b
                    case _:
                        if b == 0:
                            raise _NotMeaningful(right)
                        return a / b
            case ast.Compare(left=left, ops=[op], comparators=[right]):
                a, b = _eval(left, year, value), _eval(right, year, value)
                held = {
                    ast.Gt: a > b,
                    ast.Lt: a < b,
                    ast.GtE: a >= b,
                    ast.LtE: a <= b,
                }[type(op)]
                return Decimal(int(held))
    raise ValueError(f"can't compute {ast.unparse(node)!r}")


def _ids(used: tuple[Used, ...], inputs: Inputs) -> tuple[str, ...]:
    found = (inputs.get((u.name, u.fiscal_year)) for u in used)
    return tuple(sorted({i for f in found if f is not None for i in f.ids}))
