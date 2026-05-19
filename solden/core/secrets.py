"""Centralized secret loading with dev/prod behavior.

In dev mode (ENV != "production"), missing secrets get a random fallback
and a warning. In production, missing required secrets crash on startup.

Dual-read window for the Clearledgr → Solden rename: callers ask for
either ``SOLDEN_X`` or ``CLEARLEDGR_X`` and we look up both names,
preferring the Solden-prefixed value. This lets us add the new env vars
on Railway without removing the legacy ones in the same deploy. Once
every environment is migrated, the legacy half collapses out.
"""

import hashlib
import logging
import os
import platform

logger = logging.getLogger(__name__)

_generated_cache: dict[str, str] = {}
_legacy_warned: set[str] = set()

# Prefix translation. The dual-read helper accepts a name in either
# direction and looks up both. Callers can pass the Solden-prefixed
# name and we'll fall back to Clearledgr, or pass the legacy name and
# we'll prefer Solden.
_NEW_PREFIX = "SOLDEN_"
_OLD_PREFIX = "CLEARLEDGR_"


def _paired_names(name: str) -> tuple[str, str]:
    """Return (new_name, old_name) for the given env var.

    Accepts a name with either prefix. Names without either prefix
    are returned twice (no translation possible).
    """
    if name.startswith(_NEW_PREFIX):
        suffix = name[len(_NEW_PREFIX):]
        return name, _OLD_PREFIX + suffix
    if name.startswith(_OLD_PREFIX):
        suffix = name[len(_OLD_PREFIX):]
        return _NEW_PREFIX + suffix, name
    return name, name


def _get_with_fallback(name: str, default: str | None = None) -> str | None:
    """Read an env var, preferring the Solden-prefixed form.

    Emits a single deprecation warning per legacy name when only the
    legacy variant is set. Returns *default* if neither is set.
    """
    new_name, old_name = _paired_names(name)
    if new_name != old_name:
        new_val = os.environ.get(new_name)
        if new_val is not None and new_val != "":
            return new_val
        old_val = os.environ.get(old_name)
        if old_val is not None and old_val != "":
            if old_name not in _legacy_warned:
                _legacy_warned.add(old_name)
                logger.warning(
                    "DEPRECATED ENV VAR: %s is set; rename to %s. "
                    "Legacy name still honoured during the rename window.",
                    old_name,
                    new_name,
                )
            return old_val
        return default
    # No prefix translation — plain lookup.
    val = os.environ.get(name)
    return val if val is not None and val != "" else default


def _is_production() -> bool:
    # Treat staging as production-like for secret enforcement.
    return os.getenv("ENV", "dev").lower() in ("production", "prod", "staging", "stage")


def require_secret(name: str) -> str:
    """Return the value of an environment variable, or raise in production.

    In dev mode a random token is generated once and cached for the process
    lifetime so that callers get a stable value within a single run.
    """
    val = _get_with_fallback(name)
    if val:
        return val

    if _is_production():
        new_name, old_name = _paired_names(name)
        hint = (
            f"Set {new_name!r} (or legacy {old_name!r}) "
            "as an environment variable before starting in production."
            if new_name != old_name
            else f"Set {name!r} as an environment variable before starting in production."
        )
        raise RuntimeError(f"Required secret {name!r} is not set. {hint}")

    # Dev mode: deterministic value from hostname + secret name so cookies
    # and Fernet keys survive server restarts during development. Key by
    # the new-prefixed canonical name so a single dev value is stable
    # whether callers ask for SOLDEN_X or CLEARLEDGR_X.
    new_name, _ = _paired_names(name)
    if new_name not in _generated_cache:
        seed = f"{platform.node()}:{new_name}"
        _generated_cache[new_name] = hashlib.sha256(seed.encode()).hexdigest()
        logger.warning(
            "DEV MODE: Generated deterministic value for %s — "
            "set this env var to silence this warning.",
            new_name,
        )
    return _generated_cache[new_name]


def optional_secret(name: str, *, default: str = "") -> str:
    """Return the value of an env var, falling back to *default* silently."""
    val = _get_with_fallback(name)
    return val if val is not None else default
