"""Sphinx configuration for the pysmarthq documentation."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

project = "pysmarthq"
author = "Ryan Morash"
copyright = "2026, Ryan Morash"

try:
    release = package_version("pysmarthq")
except PackageNotFoundError:
    release = "0.1.0"
version = release

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_rtd_theme",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": True,
    "sticky_navigation": True,
    "style_external_links": True,
}
html_context = {
    "display_github": True,
    "github_user": "ryanmorash",
    "github_repo": "pysmarthq",
    "github_version": "main",
    "conf_py_path": "/docs/",
}

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_class_signature = "mixed"
autoclass_content = "both"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "aiohttp": ("https://docs.aiohttp.org/en/stable/", None),
}
intersphinx_timeout = 10

# Autodoc looks these up under the defining module or the short name.
# Inventories publish the public re-exports instead.
_EXTERNAL_TYPE_ALIASES = {
    "ClientSession": "aiohttp.ClientSession",
    "ClientTimeout": "aiohttp.ClientTimeout",
    "ClientResponse": "aiohttp.ClientResponse",
    "aiohttp.client.ClientSession": "aiohttp.ClientSession",
    "aiohttp.client.ClientTimeout": "aiohttp.ClientTimeout",
    "aiohttp.client_reqrep.ClientResponse": "aiohttp.ClientResponse",
    "aiohttp.client.ClientResponse": "aiohttp.ClientResponse",
    "Any": "typing.Any",
    "Mapping": "collections.abc.Mapping",
}


def _missing_reference(app, env, node, contnode):
    from sphinx.ext.intersphinx import resolve_reference_any_inventory

    original = node.get("reftarget")
    target = _EXTERNAL_TYPE_ALIASES.get(original)
    if target is None:
        return None
    node["reftarget"] = target
    reftype = node.get("reftype")
    try:
        resolved = resolve_reference_any_inventory(env, False, node, contnode)
        if resolved is None and target == "typing.Any":
            # typing.Any is published as py:data, and the annotation role is class.
            node["reftype"] = "data"
            resolved = resolve_reference_any_inventory(env, False, node, contnode)
        return resolved
    finally:
        node["reftarget"] = original
        node["reftype"] = reftype


def setup(app):
    app.connect("missing-reference", _missing_reference)
