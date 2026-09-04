from __future__ import annotations

from typing import Any

from .oktmo_lookup import oktmo_scope_key_profile
from .oktmo_user_keys import merge_current_keys_into_profile


def normalizer_oktmo_key_profile(normalizer: Any) -> dict[str, Any]:
    """Return the weighted OKTMO key profile used by address runtime reports."""
    use_oktmo = bool(getattr(normalizer, "use_oktmo", False))
    subject_ter_hint = getattr(normalizer, "subject_ter_hint", None) if use_oktmo else None
    municipality_hint = getattr(normalizer, "municipality_hint", None) if use_oktmo else None
    profile = oktmo_scope_key_profile(
        getattr(normalizer, "data_dir"),
        subject_ter_hint=subject_ter_hint,
        municipality_hint=municipality_hint,
    )
    return merge_current_keys_into_profile(profile, getattr(normalizer, "data_dir", None))


def normalizer_runtime_report(normalizer: Any, key_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    key_profile = key_profile if key_profile is not None else normalizer_oktmo_key_profile(normalizer)
    return {
        "city_name": getattr(normalizer, "city_name", ""),
        "data_dir": str(getattr(normalizer, "data_dir", "")),
        "use_oktmo": bool(getattr(normalizer, "use_oktmo", False)),
        "subject_ter_hint": getattr(normalizer, "subject_ter_hint", None),
        "subject_hint": getattr(normalizer, "subject_hint", None),
        "municipality_hint": getattr(normalizer, "municipality_hint", None),
        "oktmo_key_profile": key_profile,
    }
