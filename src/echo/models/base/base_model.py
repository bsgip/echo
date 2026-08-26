from pydantic import BaseModel as PydanticBaseModel


class BaseModel(PydanticBaseModel):
    """Create a modified base model with the config we want."""

    class Config:
        validate_assignment = True  # Set to true so that we re-validate when we update a model field
        extra = "ignore"  # extra attributes are ignored
        arbitrary_types_allowed = True
