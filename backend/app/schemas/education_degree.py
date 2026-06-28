from pydantic import BaseModel, ConfigDict


class EducationDegreeRead(BaseModel):
    id: int
    code: str
    label: str
    is_other: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)
