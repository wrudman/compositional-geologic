"""Register Streamlit custom components from a real imported module.

The launcher executes a selected survey with ``exec``. Newer Streamlit
versions cannot derive a module name from that synthetic caller frame.
"""

import streamlit.components.v1 as components


def declare_component(name: str, path: str):
    """Declare a local component from this normally imported module."""
    return components.declare_component(name, path=path)
