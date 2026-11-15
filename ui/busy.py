"""Short-lived busy indicators for Drive / flow / project / release work."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import streamlit as st


@contextmanager
def busy(message: str) -> Iterator[None]:
    """Show a spinner while a blocking step runs (Drive, pack, restore, …)."""
    with st.spinner(message):
        yield
