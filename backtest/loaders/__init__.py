"""Loader registry package. Importing this module registers the bundled loaders."""

from . import yfinance_loader as _yfinance_loader  # noqa: F401  -- registers "yfinance"
