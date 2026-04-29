"""Loader registry package. Importing this module registers the bundled loaders."""

from . import (
    mcx_loader as _mcx_loader,  # noqa: F401  -- registers "mcx"
    yfinance_loader as _yfinance_loader,  # noqa: F401  -- registers "yfinance"
)
