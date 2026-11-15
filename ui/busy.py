"""Short-lived busy indicators for Drive / flow / project / release work."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import streamlit as st


@contextmanager
def busy(message: str) -> Iterator[None]:
    """Show a spinner while a blocking step runs (Drive, pack, restore, …).

    Do not call this *above* widgets that were drawn on the previous run
    without a spinner — Streamlit keeps those widgets greyed (stale) until
    the script ends, which looks like a duplicated UI. Prefer ``busy_in`` on
    a stable ``st.empty()`` slot, or set a pending flag and ``st.rerun()`` so
    the spinner replaces the widget tree instead of shifting it.
    """
    with st.spinner(message):
        yield


@contextmanager
def busy_in(slot: Any, message: str) -> Iterator[None]:
    """Spinner inside a reserved ``st.empty()`` slot; clears the slot on exit."""
    with slot.container():
        with st.spinner(message):
            yield
    slot.empty()
