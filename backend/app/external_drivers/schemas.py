from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FactorType = Literal["commodity", "fx", "sector_index", "theme_etf", "unsupported_placeholder"]
Importance = Literal["core", "conditional", "context", "core_if_available"]
DriverStatus = Literal["configured", "pending_probe", "unsupported", "unavailable"]
ProfileStatus = Literal["active", "draft", "unavailable"]
MappingStatus = Literal["configured", "not_configured", "unavailable"]


class RetrievalConfig(BaseModel):
    provider: str
    endpoint: str
    provider_symbol: str | None = None
    code: str | None = None


class ExternalDriver(BaseModel):
    factor_id: str
    display_name: str
    factor_type: FactorType
    importance: Importance
    retrieval_config: RetrievalConfig
    inclusion_reason: str
    interpretation_limit: str
    status: DriverStatus = "configured"


class ExternalDriverProfile(BaseModel):
    profile_id: str
    profile_name: str
    description: str
    applies_to_symbols: list[str] = Field(default_factory=list)
    applies_to_primary_themes: list[str] = Field(default_factory=list)
    drivers: list[ExternalDriver] = Field(default_factory=list)
    boundary: str
    version: str = "external_driver_profile.v1"
    status: ProfileStatus = "active"


class ExternalDriverContext(BaseModel):
    mapping_status: MappingStatus
    profile_id: str
    symbol: str
    message: str
    future_extension: str
    drivers: list[dict[str, Any]] = Field(default_factory=list)
    boundary: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    missing_data: list[dict[str, Any]] = Field(default_factory=list)
