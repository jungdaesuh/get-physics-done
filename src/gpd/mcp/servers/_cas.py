"""Computer-algebra helpers backing executable verification checks.

These helpers turn the verification server's limiting-case and symmetry tools
from structural ``"documented"`` markers into actually-computed verdicts using
SymPy. They are deliberately conservative: any parse failure, timeout, or
genuine ambiguity downgrades to an ``INCONCLUSIVE`` verdict and never to a
``PASS``, so the oracle can never manufacture a false confirmation.

SymPy is imported lazily so importing the verification server stays cheap and
degrades gracefully (``inconclusive``) in environments where the CAS backend is
not yet installed, rather than hard-failing the whole server import.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable

# ─── Verdict vocabulary (shared with the verification server result schema) ────

VERDICT_PASS = "pass"  # computed result matches the expected result
VERDICT_FAIL = "fail"  # computed result provably differs from expected
VERDICT_COMPUTED = "computed"  # computed a real result; no machine-checkable expectation
VERDICT_INCONCLUSIVE = "inconclusive"  # could not parse / evaluate / decide — never a pass

_MAX_EXPR_LEN = 2000
_DEFAULT_TIMEOUT_S = 4.0

# Identifiers kept as SymPy callables/constants instead of being rebound to
# plain Symbols, so exp()/sin()/sqrt()/oo still work. Every other identifier
# (gamma, E, I, c, m, T, g, ...) is forced to a plain Symbol so physics notation
# is not silently reinterpreted as a SymPy special function or constant.
_FUNCTION_WHITELIST = frozenset(
    {
        "sin", "cos", "tan", "cot", "sec", "csc",
        "asin", "acos", "atan", "atan2",
        "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
        "exp", "log", "ln", "sqrt", "Abs", "re", "im",
        "oo", "pi",
    }
)

# Reject obviously unsafe tokens before handing a string to the parser.
_UNSAFE = re.compile(
    r"(__|\bimport\b|\blambda\b|\bexec\b|\beval\b|\bopen\b|"
    r"\bos\b|\bsys\b|\bsubprocess\b|\bgetattr\b|\bglobals\b|;|`|:=)"
)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_INF = re.compile(r"\b(?:infinity|infty|inf)\b", re.IGNORECASE)

# ─── LaTeX support ─────────────────────────────────────────────────────────────
#
# Physics derivations are written in LaTeX, so the oracle also accepts LaTeX
# expressions. They are parsed with SymPy's grammar-based lark backend (which
# cannot execute code, unlike sympify). The lark grammar covers fractions,
# powers, roots, subscripts, most Greek letters, and standard functions, but
# rejects a handful of common macros (\hbar, \Omega, ...) and juxtaposed
# superscripted products (``a^2 b^2``). Unsupported macros are rewritten to a
# collision-free placeholder and substituted back; anything still unparseable
# returns None (→ inconclusive), never a false PASS.

# Macros lark rejects but that are common in physics → intended Symbol name.
_LATEX_SYMBOL_FIXUPS = {r"\hbar": "hbar", r"\Omega": "Omega", r"\sigma": "sigma", r"\ell": "ell"}
# Macros mapped to genuine SymPy constants rather than free symbols.
_LATEX_CONST_FIXUPS = (r"\pi",)  # → sympy.pi
# Supported single-token macros used as collision-free placeholders.
_LATEX_PLACEHOLDERS = (r"\eta", r"\zeta", r"\xi", r"\chi", r"\kappa", r"\iota", r"\upsilon", r"\digamma")
# Spacing / delimiter macros stripped before parsing.
_LATEX_STRIP = (r"\left", r"\right", r"\quad", r"\qquad", r"\,", r"\;", r"\:", r"\!", r"\(", r"\)", r"\[", r"\]")
# TeX constructs refused outright (environments / macro definitions / file IO).
_LATEX_DANGEROUS = re.compile(
    r"\\(?:input|include|def|csname|write|read|openin|catcode|immediate|loop|"
    r"expandafter|newcommand|renewcommand|usepackage|begin|end)\b"
)
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")
# Arrow macros normalized to '->' when parsing a limit description.
_LATEX_ARROW = re.compile(r"\\(?:to|rightarrow|longrightarrow|mapsto)\b")


def _sympy():  # pragma: no cover - thin lazy import
    import sympy

    return sympy


def _looks_like_latex(text: str) -> bool:
    """Heuristic: does the string contain LaTeX math markup?"""
    return bool(_LATEX_COMMAND.search(text)) or "^{" in text or "_{" in text


def _parse_latex(text: str):
    """Parse a LaTeX physics expression into a SymPy object, or ``None``.

    Uses the grammar-based lark backend (no code execution), rewriting the
    common lark-unsupported macros to placeholders and substituting them back.
    """
    cleaned = text.strip().strip("$").replace("&", " ")
    if _LATEX_DANGEROUS.search(cleaned):
        return None
    for token in _LATEX_STRIP:
        cleaned = cleaned.replace(token, " ")
    if "=" in cleaned:
        cleaned = cleaned.split("=")[-1].strip()
    if not cleaned:
        return None
    try:
        sympy = _sympy()
        from sympy.parsing.latex import parse_latex
    except Exception:  # noqa: BLE001 - sympy/lark unavailable → unparseable
        return None

    substitutions = {}
    pool = [p for p in _LATEX_PLACEHOLDERS if p not in cleaned]
    fixups = [(m, _LATEX_SYMBOL_FIXUPS[m]) for m in _LATEX_SYMBOL_FIXUPS]
    fixups += [(m, None) for m in _LATEX_CONST_FIXUPS]
    try:
        for macro, name in fixups:
            pattern = re.escape(macro) + r"(?![A-Za-z])"
            if re.search(pattern, cleaned):
                if not pool:
                    return None
                placeholder = pool.pop(0)
                cleaned = re.sub(pattern, lambda _m, ph=placeholder: ph, cleaned)
                target = sympy.pi if name is None else sympy.Symbol(name)
                substitutions[sympy.Symbol(placeholder.lstrip("\\"))] = target
    except Exception:  # noqa: BLE001
        return None

    ok, parsed = run_with_timeout(lambda: parse_latex(cleaned, backend="lark"))
    if not ok or parsed is None:
        return None
    if not substitutions:
        return parsed
    ok2, substituted = run_with_timeout(lambda: parsed.subs(substitutions))
    return substituted if ok2 else None


def run_with_timeout(fn: Callable[[], object], timeout_s: float = _DEFAULT_TIMEOUT_S) -> tuple[bool, object]:
    """Run ``fn()`` in a daemon worker thread.

    Returns ``(ok, value)`` on success or ``(False, reason)`` on timeout/error.
    A timed-out thread cannot be killed, but as a daemon it never blocks the
    response and is bounded by the caller's input-size cap.
    """
    box: dict[str, object] = {}

    def worker() -> None:
        try:
            box["value"] = fn()
            box["ok"] = True
        except BaseException as exc:  # noqa: BLE001 - report, never propagate
            box["ok"] = False
            box["reason"] = type(exc).__name__

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        return False, "timeout"
    if box.get("ok"):
        return True, box.get("value")
    return False, box.get("reason", "error")


def safe_parse(text: str):
    """Parse a physics expression string into a SymPy object, or ``None``.

    Conservative by design: rejects unsafe tokens, caps length, forces unknown
    identifiers to plain Symbols, normalizes ``^``/``infinity`` notation, takes
    the right-hand side of an equation (we reason about the formula), and
    returns ``None`` on any failure.
    """
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw or len(raw) > _MAX_EXPR_LEN:
        return None
    if _looks_like_latex(raw):
        return _parse_latex(raw)
    if _UNSAFE.search(raw):
        return None
    if "=" in raw:
        raw = raw.split("=")[-1].strip()
        if not raw:
            return None
    normalized = _INF.sub("oo", raw).replace("^", "**")
    try:
        sympy = _sympy()
        from sympy.parsing.sympy_parser import parse_expr, standard_transformations

        local = {
            name: sympy.Symbol(name)
            for name in set(_IDENT.findall(normalized))
            if name not in _FUNCTION_WHITELIST
        }
        ok, value = run_with_timeout(
            lambda: parse_expr(
                normalized,
                local_dict=local,
                transformations=standard_transformations,
                evaluate=True,
            )
        )
        if not ok:
            return None
        return value
    except Exception:  # noqa: BLE001 - any parse/import failure → unparseable
        return None


def symbolic_equal(a, b, timeout_s: float = _DEFAULT_TIMEOUT_S):
    """Return ``True``/``False``/``None`` for whether two expressions are equal.

    ``None`` means "could not decide" — callers must treat it as inconclusive,
    never as equal.
    """
    try:
        sympy = _sympy()
    except Exception:  # noqa: BLE001
        return None

    def _check():
        diff = sympy.simplify(a - b)
        if diff == 0:
            return True
        verdict = a.equals(b)  # robust numeric+symbolic probe; may return None
        if verdict is True:
            return True
        if verdict is False:
            return False
        if diff.is_number and diff != 0:
            return False
        return None

    ok, value = run_with_timeout(_check, timeout_s)
    return value if ok else None


def parse_limit_target(description: str) -> tuple[str, str] | None:
    """Parse a limit description into ``(variable, point_text)`` or ``None``.

    Accepts ``"hbar -> 0"``, ``"c -> infinity"``, LaTeX arrows/macros such as
    ``r"\\hbar \\to 0"`` and ``r"c \\to \\infty"``, and descriptive prefixes such
    as ``"classical limit: hbar -> 0"`` (uses the last ``X -> Y`` occurrence).
    A composite ratio such as ``"v/c -> 0"`` is intentionally rejected because
    it is not a single limit variable.
    """
    if not isinstance(description, str):
        return None
    normalized = _LATEX_ARROW.sub("->", description.replace("$", ""))
    if "->" not in normalized:
        return None
    # An optional leading backslash lets LaTeX symbols (\hbar) match.
    matches = re.findall(r"(\\?[A-Za-z_][A-Za-z0-9_/]*)\s*->\s*([^,;]+)", normalized)
    if not matches:
        return None
    var_raw, point_raw = matches[-1]
    var = var_raw.lstrip("\\").strip()
    if "/" in var or not var:
        return None
    return var, point_raw.strip()


def check_limit(expression: str, limit_description: str, expected: str, timeout_s: float = _DEFAULT_TIMEOUT_S) -> dict:
    """Compute ``lim_{var->point} expression`` and compare to ``expected``.

    Returns an additive ``cas`` payload describing what was actually executed.
    The verdict is one of pass/fail/computed/inconclusive.
    """
    target = parse_limit_target(limit_description)
    if target is None:
        return {
            "attempted": False,
            "verdict": VERDICT_INCONCLUSIVE,
            "detail": "no machine-readable 'var -> point' in limit description",
        }
    var_name, point_text = target

    expr = safe_parse(expression)
    if expr is None:
        return {
            "attempted": False,
            "verdict": VERDICT_INCONCLUSIVE,
            "variable": var_name,
            "point": point_text,
            "detail": "expression is not machine-parseable",
        }
    point = safe_parse(point_text)
    if point is None:
        return {
            "attempted": False,
            "verdict": VERDICT_INCONCLUSIVE,
            "variable": var_name,
            "point": point_text,
            "detail": f"limit point '{point_text}' is not machine-parseable",
        }

    sympy = _sympy()
    var = sympy.Symbol(var_name)
    ok, value = run_with_timeout(lambda: sympy.limit(expr, var, point), timeout_s)
    if not ok:
        return {
            "attempted": True,
            "verdict": VERDICT_INCONCLUSIVE,
            "variable": var_name,
            "point": point_text,
            "detail": f"SymPy could not evaluate the limit ({value})",
        }

    payload: dict[str, object] = {
        "attempted": True,
        "variable": var_name,
        "point": point_text,
        "computed_limit": str(value),
    }
    expected_expr = safe_parse(expected)
    if expected_expr is None:
        payload["verdict"] = VERDICT_COMPUTED
        payload["expected_parsed"] = False
        payload["detail"] = "computed the limit; expected result is prose — compare the computed_limit manually"
        return payload

    payload["expected_parsed"] = True
    equal = symbolic_equal(value, expected_expr, timeout_s)
    if equal is True:
        payload["verdict"] = VERDICT_PASS
        payload["detail"] = "computed limit matches the expected result"
    elif equal is False:
        payload["verdict"] = VERDICT_FAIL
        payload["detail"] = "computed limit provably differs from the expected result"
    else:
        payload["verdict"] = VERDICT_COMPUTED
        payload["detail"] = "equality is undecidable — review computed_limit vs expected"
    return payload


# Substitution-based symmetries we can execute: name fragment → (transform var, label).
_PARITY_VARS = ("x", "r")
_TIME_VARS = ("t",)


def _pick_variable(free_names: list[str], preferred: tuple[str, ...]) -> str | None:
    for name in preferred:
        if name in free_names:
            return name
    if len(free_names) == 1:
        return free_names[0]
    return None


def check_symmetry(expression: str, symmetry: str, timeout_s: float = _DEFAULT_TIMEOUT_S) -> dict:
    """Execute a coordinate-reflection symmetry check where one is well-defined.

    Handles parity (``x -> -x``) and time-reversal (``t -> -t``) by substitution
    and classifies the expression as invariant (even) / odd / neither. Other
    symmetries (gauge, Lorentz, ...) have no single-substitution test and return
    inconclusive so the structural ``status`` field still drives those.
    """
    name = symmetry.lower().replace("_", " ").replace("-", " ")
    expr = safe_parse(expression)
    if expr is None:
        return {
            "attempted": False,
            "verdict": VERDICT_INCONCLUSIVE,
            "detail": "expression is not machine-parseable",
        }

    free_names = sorted(str(s) for s in expr.free_symbols)
    if "parity" in name:
        var_name = _pick_variable(free_names, _PARITY_VARS)
    elif "time" in name and "revers" in name:
        var_name = _pick_variable(free_names, _TIME_VARS)
    else:
        return {
            "attempted": False,
            "verdict": VERDICT_INCONCLUSIVE,
            "detail": "no single-substitution transformation defined for this symmetry",
        }

    if var_name is None:
        return {
            "attempted": False,
            "verdict": VERDICT_INCONCLUSIVE,
            "detail": "could not unambiguously identify the variable to transform",
        }

    sympy = _sympy()
    var = sympy.Symbol(var_name)
    ok, transformed = run_with_timeout(lambda: expr.subs(var, -var), timeout_s)
    if not ok:
        return {
            "attempted": True,
            "verdict": VERDICT_INCONCLUSIVE,
            "transformation": f"{var_name} -> -{var_name}",
            "detail": f"substitution failed ({transformed})",
        }

    even = symbolic_equal(transformed, expr, timeout_s)
    odd = symbolic_equal(transformed, -expr, timeout_s)
    if even is True:
        classification, invariant = "invariant (even)", True
    elif odd is True:
        classification, invariant = "odd", False
    elif even is False and odd is False:
        classification, invariant = "neither even nor odd", False
    else:
        return {
            "attempted": True,
            "verdict": VERDICT_INCONCLUSIVE,
            "transformation": f"{var_name} -> -{var_name}",
            "transformed_expression": str(transformed),
            "detail": "could not classify behavior under the transformation",
        }

    return {
        "attempted": True,
        "verdict": VERDICT_COMPUTED,
        "transformation": f"{var_name} -> -{var_name}",
        "transformed_expression": str(transformed),
        "classification": classification,
        "invariant": invariant,
        "detail": f"expression is {classification} under {var_name} -> -{var_name}",
    }
