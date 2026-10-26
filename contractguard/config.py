"""Configuration loader.

Values come from ``config/settings.yaml``; environment variables (and ``.env``) override them.
Nested values use the ``CG_`` prefix with ``__`` as the delimiter, e.g. ``CG_LLM__RPM=4``.
The short names in ``.env.example`` (``LLM_PROVIDER``, ``LLM_MODEL``, ``GEMINI_API_KEY``)
are also accepted.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    return Path(os.environ.get("CG_CONFIG_DIR", REPO_ROOT / "config"))


def load_yaml(name: str) -> dict[str, Any]:
    """Load ``config/<name>`` as a dict. Raises FileNotFoundError if absent."""
    path = config_dir() / name
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


class LimitsSettings(BaseModel):
    max_file_mb: int
    max_pages: int
    max_docx_words: int


class OCRSettings(BaseModel):
    min_chars_per_page: int
    dpi: int
    warn_confidence: float
    tesseract_cmd: str | None = None
    lang: str = "eng"


class SegmentationSettings(BaseModel):
    min_chars: int
    max_chars: int
    fallback_min_headings: int


class ClassificationSettings(BaseModel):
    model_path: str
    thresholds_path: str


class EmbeddingSettings(BaseModel):
    model_name: str
    proto_threshold: float
    prototypes_path: str


class PolicySettings(BaseModel):
    default_policy_id: str
    tau_missing: float
    policies_dir: str = "policies"


class LLMSettings(BaseModel):
    provider: Literal["gemini", "ollama", "mock", "none"]
    model: str | None = None
    ollama_host: str = "http://localhost:11434"
    rpm: int
    max_findings: int
    temperature: float
    timeout_s: int
    max_retries: int


class OrgSettings(BaseModel):
    default_name: str
    date_order: Literal["DMY", "MDY", "YMD"]


class FrontendSettings(BaseModel):
    api_url: str
    poll_seconds: float
    origin: str = "http://localhost:8501"  # Streamlit origin allowed by CORS


class PathSettings(BaseModel):
    data_dir: str = "data"
    uploads_dir: str = "data/uploads"
    sqlite_path: str = "data/contractguard.db"
    models_dir: str = "models"


class _YamlSource(PydanticBaseSettingsSource):
    def get_field_value(self, field, field_name):  # pragma: no cover - unused
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return load_yaml("settings.yaml")


class _ShortEnvSource(PydanticBaseSettingsSource):
    """Maps the flat names used in .env.example onto nested settings."""

    def get_field_value(self, field, field_name):  # pragma: no cover - unused
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        llm: dict[str, Any] = {}
        if os.environ.get("LLM_PROVIDER"):
            llm["provider"] = os.environ["LLM_PROVIDER"]
        if os.environ.get("LLM_MODEL"):
            llm["model"] = os.environ["LLM_MODEL"]
        return {"llm": llm} if llm else {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CG_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    limits: LimitsSettings
    ocr: OCRSettings
    segmentation: SegmentationSettings
    classification: ClassificationSettings
    embeddings: EmbeddingSettings
    policy: PolicySettings
    llm: LLMSettings
    org: OrgSettings
    frontend: FrontendSettings
    paths: PathSettings = PathSettings()
    disclaimer: str
    gemini_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("GEMINI_API_KEY", "CG_GEMINI_API_KEY")
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Earlier sources win.
        return (
            init_settings,
            env_settings,
            _ShortEnvSource(settings_cls),
            dotenv_settings,
            _YamlSource(settings_cls),
        )

    def resolve_path(self, relative: str) -> Path:
        """Resolve a settings path relative to the repository root."""
        p = Path(relative)
        return p if p.is_absolute() else REPO_ROOT / p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_patterns() -> dict[str, Any]:
    return load_yaml("patterns.yaml")


@lru_cache(maxsize=1)
def get_label_map() -> dict[str, Any]:
    return load_yaml("label_map.yaml")


@lru_cache(maxsize=1)
def get_contract_types() -> dict[str, Any]:
    return load_yaml("contract_types.yaml")


@lru_cache(maxsize=1)
def get_templates() -> dict[str, Any]:
    return load_yaml("templates.yaml")


def clear_caches() -> None:
    for fn in (get_settings, get_patterns, get_label_map, get_contract_types, get_templates):
        fn.cache_clear()
