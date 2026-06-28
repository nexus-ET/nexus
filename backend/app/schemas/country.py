from pydantic import BaseModel, ConfigDict


class CountryRead(BaseModel):
    id: int
    iso2: str
    name: str
    dial_code: str
    sort_order: int

    model_config = ConfigDict(from_attributes=True)
