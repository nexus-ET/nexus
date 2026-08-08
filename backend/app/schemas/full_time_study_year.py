from pydantic import BaseModel, ConfigDict


class FullTimeStudyYearRead(BaseModel):
    id: int
    code: str
    label: str
    level_id: int
    level_code: str | None = None
    level_name: str | None = None
    sort_order: int

    model_config = ConfigDict(from_attributes=True)
