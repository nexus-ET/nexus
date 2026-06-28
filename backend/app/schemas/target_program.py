from pydantic import BaseModel


class TargetProgramRead(BaseModel):
    id: int
    code: str
    label: str
    sort_order: int

    model_config = {"from_attributes": True}


class TargetCourseRead(BaseModel):
    id: int
    code: str
    label: str
    program_code: str
    sort_order: int

    model_config = {"from_attributes": True}
