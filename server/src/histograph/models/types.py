from typing import Literal

from pydantic import Field

from histograph.core.events import EventModel

JsonScalar = bool | int | float | str


class ModelDefinition(EventModel):
    name: str = Field(min_length=1, max_length=200)
    task: Literal["binary_classification"]
    positive_class: str = Field(min_length=1, max_length=200)
    positive_actual: JsonScalar
    datahub_urn: str | None = Field(default=None, min_length=1, max_length=500)
