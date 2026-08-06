from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError


class SqlAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class SqlAnalysis:
    tables: frozenset[str]
    columns: frozenset[str]


def analyze_sql(sql: str, dialect: str | None = None) -> SqlAnalysis:
    try:
        expressions = parse(sql, read=dialect)
    except ParseError as error:
        raise SqlAnalysisError(str(error)) from error
    if not expressions:
        raise SqlAnalysisError("SQL was empty")
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter)
    if any(expression.find(*forbidden) for expression in expressions):
        raise SqlAnalysisError("Only read-only SQL statements are allowed")
    tables = {
        _normalize_identifier(table.sql(dialect=dialect))
        for expression in expressions
        for table in expression.find_all(exp.Table)
    }
    columns = {
        _normalize_identifier(column.sql(dialect=dialect))
        for expression in expressions
        for column in expression.find_all(exp.Column)
    }
    return SqlAnalysis(tables=frozenset(tables), columns=frozenset(columns))


def identifier_matches(actual: str, expected: str) -> bool:
    actual_normalized = _normalize_identifier(actual)
    expected_normalized = _normalize_identifier(expected)
    return (
        actual_normalized == expected_normalized
        or actual_normalized.endswith(f".{expected_normalized}")
        or expected_normalized.endswith(f".{actual_normalized}")
    )


def _normalize_identifier(value: str) -> str:
    return value.replace('"', "").replace("`", "").replace("[", "").replace("]", "").lower()
