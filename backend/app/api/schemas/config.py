from __future__ import annotations

from pydantic import BaseModel


class OperatorConfigField(BaseModel):
    key: str
    value: str
    has_value: bool
    editable: bool
    secret: bool
    restart_required: bool
    description: str


class OperatorConfigResponse(BaseModel):
    fields: list[OperatorConfigField]


class OperatorConfigWriteRequest(BaseModel):
    fields: dict[str, str]


class OperatorConfigRejectedField(BaseModel):
    key: str
    reason: str


class OperatorConfigWriteResponse(BaseModel):
    written: list[str]
    rejected: list[OperatorConfigRejectedField]