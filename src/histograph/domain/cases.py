from pydantic import Field, model_validator

from histograph.domain.base import DomainModel


class AssetAssertions(DomainModel):
    required: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    requires_any_of: tuple[tuple[str, ...], ...] = ()


class SqlAssertions(DomainModel):
    dialect: str | None = None
    required_tables: tuple[str, ...] = ()
    forbidden_tables: tuple[str, ...] = ()
    required_columns: tuple[str, ...] = ()
    forbidden_columns: tuple[str, ...] = ()
    require_query: bool = True


class ResultAssertions(DomainModel):
    required_columns: tuple[str, ...] = ()
    min_rows: int | None = Field(default=None, ge=0)
    max_rows: int | None = Field(default=None, ge=0)
    max_null_fraction: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_row_range(self) -> "ResultAssertions":
        if self.min_rows is not None and self.max_rows is not None:
            if self.min_rows > self.max_rows:
                raise ValueError("min_rows cannot exceed max_rows")
        invalid = [value for value in self.max_null_fraction.values() if not 0 <= value <= 1]
        if invalid:
            raise ValueError("max_null_fraction values must be between 0 and 1")
        return self


class ResponseAssertions(DomainModel):
    required_phrases: tuple[str, ...] = ()
    forbidden_phrases: tuple[str, ...] = ()


class TestCase(DomainModel):
    __test__ = False

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=10_000)
    context_query: str | None = Field(default=None, max_length=1_000)
    assets: AssetAssertions = Field(default_factory=AssetAssertions)
    sql: SqlAssertions = Field(default_factory=SqlAssertions)
    result: ResultAssertions = Field(default_factory=ResultAssertions)
    response: ResponseAssertions = Field(default_factory=ResponseAssertions)
