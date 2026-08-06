from collections.abc import Iterable
from typing import Any

from histograph.domain import (
    EvaluationFinding,
    EvaluationReport,
    EvaluationStatus,
    ExecutionEvidence,
    FindingLevel,
    SqlAssertions,
    SqlExecution,
    TestCase,
)
from histograph.evaluation.sql import SqlAnalysisError, analyze_sql, identifier_matches


class EvaluationEngine:
    def evaluate(self, test_case: TestCase, evidence: ExecutionEvidence) -> EvaluationReport:
        findings: list[EvaluationFinding] = []
        findings.extend(self._evaluate_assets(test_case, evidence))
        findings.extend(self._evaluate_sql(test_case.sql, evidence.sql_executions))
        findings.extend(self._evaluate_result(test_case, evidence.sql_executions))
        findings.extend(self._evaluate_response(test_case, evidence.final_response))
        if evidence.errors:
            findings.append(
                EvaluationFinding(
                    code="agent.errors",
                    message="The agent emitted execution errors",
                    passed=False,
                    level=FindingLevel.ERROR,
                    evidence={"errors": list(evidence.errors)},
                )
            )
        failed = any(
            not finding.passed and finding.level is FindingLevel.ERROR for finding in findings
        )
        status = EvaluationStatus.FAILED if failed else EvaluationStatus.PASSED
        return EvaluationReport(status=status, findings=tuple(findings))

    @staticmethod
    def _evaluate_assets(
        test_case: TestCase,
        evidence: ExecutionEvidence,
    ) -> Iterable[EvaluationFinding]:
        selected = set(evidence.selected_asset_urns)
        for required in test_case.assets.required:
            passed = required in selected
            yield EvaluationFinding(
                code="asset.required",
                message=(
                    f"Required asset was used: {required}"
                    if passed
                    else f"Required asset was not used: {required}"
                ),
                passed=passed,
                level=FindingLevel.INFO if passed else FindingLevel.ERROR,
                evidence={"asset": required},
            )
        for forbidden in test_case.assets.forbidden:
            passed = forbidden not in selected
            yield EvaluationFinding(
                code="asset.forbidden",
                message=(
                    f"Forbidden asset was not used: {forbidden}"
                    if passed
                    else f"Forbidden asset was used: {forbidden}"
                ),
                passed=passed,
                level=FindingLevel.INFO if passed else FindingLevel.ERROR,
                evidence={"asset": forbidden},
            )
        for group in test_case.assets.requires_any_of:
            used = sorted(set(group).intersection(selected))
            passed = bool(used)
            yield EvaluationFinding(
                code="asset.requires-any-of",
                message=(
                    f"At least one approved asset was used: {', '.join(used)}"
                    if passed
                    else f"None of the approved assets were used: {', '.join(group)}"
                ),
                passed=passed,
                level=FindingLevel.INFO if passed else FindingLevel.ERROR,
                evidence={"allowed": list(group), "used": used},
            )

    @staticmethod
    def _evaluate_sql(
        assertions: SqlAssertions,
        executions: tuple[SqlExecution, ...],
    ) -> Iterable[EvaluationFinding]:
        if assertions.require_query and not executions:
            yield EvaluationFinding(
                code="sql.required",
                message="The agent did not execute SQL",
                passed=False,
                level=FindingLevel.ERROR,
            )
            return
        analyses = []
        for execution in executions:
            try:
                analyses.append(analyze_sql(execution.sql, assertions.dialect))
            except SqlAnalysisError as error:
                yield EvaluationFinding(
                    code="sql.invalid",
                    message=f"SQL could not be safely analysed: {error}",
                    passed=False,
                    level=FindingLevel.ERROR,
                    evidence={"sql": execution.sql},
                )
        tables = {table for analysis in analyses for table in analysis.tables}
        columns = {column for analysis in analyses for column in analysis.columns}
        for required in assertions.required_tables:
            yield _identifier_finding("table", "required", required, tables)
        for forbidden in assertions.forbidden_tables:
            yield _identifier_finding("table", "forbidden", forbidden, tables)
        for required in assertions.required_columns:
            yield _identifier_finding("column", "required", required, columns)
        for forbidden in assertions.forbidden_columns:
            yield _identifier_finding("column", "forbidden", forbidden, columns)

    @staticmethod
    def _evaluate_result(
        test_case: TestCase,
        executions: tuple[SqlExecution, ...],
    ) -> Iterable[EvaluationFinding]:
        assertions = test_case.result
        if not executions:
            return
        result = executions[-1]
        columns = set(result.columns)
        for required in assertions.required_columns:
            passed = required in columns
            yield EvaluationFinding(
                code="result.column-required",
                message=(
                    f"Required result column was returned: {required}"
                    if passed
                    else f"Required result column was not returned: {required}"
                ),
                passed=passed,
                level=FindingLevel.INFO if passed else FindingLevel.ERROR,
                evidence={"actual_columns": list(result.columns)},
            )
        row_count = len(result.rows)
        if assertions.min_rows is not None:
            passed = row_count >= assertions.min_rows
            yield _row_count_finding("minimum", assertions.min_rows, row_count, passed)
        if assertions.max_rows is not None:
            passed = row_count <= assertions.max_rows
            yield _row_count_finding("maximum", assertions.max_rows, row_count, passed)
        for column, maximum in assertions.max_null_fraction.items():
            fraction = _null_fraction(result, column)
            passed = fraction is not None and fraction <= maximum
            yield EvaluationFinding(
                code="result.null-fraction",
                message=(
                    f"Null fraction for {column} is within the allowed limit"
                    if passed
                    else (
                        f"Null fraction for {column} exceeds the allowed limit "
                        "or cannot be measured"
                    )
                ),
                passed=passed,
                level=FindingLevel.INFO if passed else FindingLevel.ERROR,
                evidence={"column": column, "actual": fraction, "maximum": maximum},
            )

    @staticmethod
    def _evaluate_response(
        test_case: TestCase,
        response: str,
    ) -> Iterable[EvaluationFinding]:
        normalized = response.casefold()
        for phrase in test_case.response.required_phrases:
            passed = phrase.casefold() in normalized
            yield EvaluationFinding(
                code="response.phrase-required",
                message=(
                    f"Required response phrase was present: {phrase}"
                    if passed
                    else f"Required response phrase was missing: {phrase}"
                ),
                passed=passed,
                level=FindingLevel.INFO if passed else FindingLevel.ERROR,
                evidence={"phrase": phrase},
            )
        for phrase in test_case.response.forbidden_phrases:
            passed = phrase.casefold() not in normalized
            yield EvaluationFinding(
                code="response.phrase-forbidden",
                message=(
                    f"Forbidden response phrase was absent: {phrase}"
                    if passed
                    else f"Forbidden response phrase was present: {phrase}"
                ),
                passed=passed,
                level=FindingLevel.INFO if passed else FindingLevel.ERROR,
                evidence={"phrase": phrase},
            )


def _identifier_finding(
    identifier_type: str,
    mode: str,
    expected: str,
    actual: set[str],
) -> EvaluationFinding:
    is_required = mode == "required"
    matched = any(identifier_matches(value, expected) for value in actual)
    passed = matched if is_required else not matched
    expectation = "was used" if is_required else "was not used"
    failure = "was not used" if is_required else "was used"
    return EvaluationFinding(
        code=f"sql.{identifier_type}-{mode}",
        message=(
            f"{mode.title()} {identifier_type} {expectation if passed else failure}: {expected}"
        ),
        passed=passed,
        level=FindingLevel.INFO if passed else FindingLevel.ERROR,
        evidence={"expected": expected, "actual": sorted(actual)},
    )


def _row_count_finding(mode: str, expected: int, actual: int, passed: bool) -> EvaluationFinding:
    return EvaluationFinding(
        code=f"result.row-count-{mode}",
        message=(
            f"Result row count satisfies the {mode}"
            if passed
            else f"Result row count does not satisfy the {mode}"
        ),
        passed=passed,
        level=FindingLevel.INFO if passed else FindingLevel.ERROR,
        evidence={"expected": expected, "actual": actual},
    )


def _null_fraction(result: SqlExecution, column: str) -> float | None:
    if column not in result.columns:
        return None
    if not result.rows:
        return 0
    index = result.columns.index(column)
    nulls = 0
    for row in result.rows:
        value: Any
        if isinstance(row, dict):
            value = row.get(column)
        elif isinstance(row, (list, tuple)) and index < len(row):
            value = row[index]
        else:
            return None
        nulls += value is None
    return nulls / len(result.rows)
