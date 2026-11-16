from pydantic import BaseModel, Field, model_validator


class CropData(BaseModel):
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)
    secondX: float = Field(ge=0, allow_inf_nan=False)
    secondY: float = Field(ge=0, allow_inf_nan=False)
    imageDir: str = Field(..., alias="image-dir", min_length=1)

    @model_validator(mode="after")
    def check_rectangle(self):
        if self.secondX <= self.x or self.secondY <= self.y:
            raise ValueError("Select a rectangle with positive width and height.")
        return self
