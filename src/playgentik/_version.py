"""Single source of truth for the installed version.

Imported by __init__.py (as playgentik.__version__), mcp.py (as the MCP
initialize handshake's self-reported clientInfo.version), and read by
pyproject.toml at build time (see [tool.setuptools.dynamic]) - one place
to bump on release instead of three copies that can drift out of sync
with each other, which is exactly what happened before this file existed
(CLIENT_INFO in mcp.py was still hardcoded at "0.1.0" after __init__.py
and pyproject.toml had already moved to a newer version).
"""

__version__ = "0.2.0"
