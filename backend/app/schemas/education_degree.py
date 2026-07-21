from pydantic import BaseModel, ConfigDict


class EducationDegreeRead(BaseModel):
    id: int
    level_id: int
    level_code: str | None = None
    level_name: str | None = None
    code: str
    label: str
    is_other: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)
