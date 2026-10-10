# backend/commons/schemas.py
from pydantic import BaseModel, Field

class CropData(BaseModel):
    x: float
    y: float
    secondX: float
    secondY: float
    imageDir: str = Field(..., alias="image-dir")