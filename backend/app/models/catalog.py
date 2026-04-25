from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backend.app.core.paths import CONFIG_DIR, REPO_ROOT


class ModelCatalogError(RuntimeError):
    """Base error for model catalog failures."""


class ModelNotFoundError(ModelCatalogError):
    """Raised when a requested model family or model name is absent."""


@dataclass(frozen=True)
class ModelEntry:
    family: str
    name: str
    config: dict[str, Any]

    @property
    def local_path(self) -> Path:
        raw_path = self.config.get("local_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ModelNotFoundError(
                f"model '{self.name}' in family '{self.family}' has no local_path"
            )
        path = Path(raw_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path

    @property
    def source(self) -> dict[str, Any]:
        source = self.config.get("source", {})
        if not isinstance(source, dict):
            raise ModelCatalogError(
                f"model '{self.name}' in family '{self.family}' has invalid source metadata"
            )
        return source


def catalog_path(family: str) -> Path:
    if not family or not family.strip():
        raise ModelNotFoundError("model family must be provided")
    return CONFIG_DIR / "models" / f"{family}.yaml"


def load_catalog(family: str) -> dict[str, Any]:
    path = catalog_path(family)
    if not path.exists():
        raise ModelNotFoundError(f"model catalog not found for family '{family}': {path}")
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ModelCatalogError(f"model catalog for family '{family}' must be a mapping: {path}")
    return data


def list_models(family: str) -> dict[str, dict[str, Any]]:
    data = load_catalog(family)
    models = data.get("models", {})
    if not isinstance(models, dict):
        raise ModelCatalogError(f"model catalog for family '{family}' has invalid models section")
    return {name: config for name, config in models.items() if isinstance(name, str) and isinstance(config, dict)}


def get_model_entry(family: str, model_name: str | None = None) -> ModelEntry:
    models = list_models(family)
    if not models:
        raise ModelNotFoundError(f"no models declared for family '{family}'")

    selected_name = model_name
    if selected_name is None:
        catalog = load_catalog(family)
        default_model = catalog.get("default_model")
        if isinstance(default_model, str) and default_model:
            selected_name = default_model
        elif len(models) == 1:
            selected_name = next(iter(models))
        else:
            raise ModelNotFoundError(
                f"model name required for family '{family}' because no unique default exists"
            )

    if selected_name not in models:
        raise ModelNotFoundError(f"model '{selected_name}' not found in family '{family}'")
    return ModelEntry(family=family, name=selected_name, config=models[selected_name])


def get_model_path(family: str, model_name: str | None = None) -> Path:
    return get_model_entry(family, model_name).local_path