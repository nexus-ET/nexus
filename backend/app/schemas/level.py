from pydantic import BaseModel, ConfigDict, Field


class LevelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)
    description: str | None = None


class LevelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None


class LevelRead(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)
