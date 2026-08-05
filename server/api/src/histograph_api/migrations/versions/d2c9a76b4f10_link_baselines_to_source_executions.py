"""link baselines to source executions

Revision ID: d2c9a76b4f10
Revises: fdfa1cec5187
Create Date: 2026-08-05 23:55:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d2c9a76b4f10"
down_revision: str | Sequence[str] | None = "fdfa1cec5187"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_baseline_versions_source_execution_id",
        "baseline_versions",
        ["source_execution_id"],
    )
    op.create_foreign_key(
        "fk_baseline_versions_source_execution_id_test_executions",
        "baseline_versions",
        "test_executions",
        ["source_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_baseline_versions_source_execution_id_test_executions",
        "baseline_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_baseline_versions_source_execution_id",
        "baseline_versions",
        type_="unique",
    )
