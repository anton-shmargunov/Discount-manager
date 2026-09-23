"""
Streamlit first-load light theme bootstrap.

Single source of truth for theme colors/font (mirrors .streamlit/config.toml).
Call apply_page_theme() immediately after st.set_page_config() on every page.
"""

from __future__ import annotations

import json

# Keep in sync with .streamlit/config.toml [theme] section.
PBA_THEME: dict[str, str] = {
    "primaryColor": "#2563eb",
    "backgroundColor": "#ffffff",
    "secondaryBackgroundColor": "#f8fafc",
    "textColor": "#111827",
    "bodyFont": "sans serif",
}

PBA_THEME_NAME = "Custom Theme"
STREAMLIT_THEME_CACHE_VERSION = 1

# Streamlit multi-page routes (01_ prefix stripped from filename).
KNOWN_APP_PATHS: list[str] = ["/", "/Correlation_Analysis"]

_FORCE_LIGHT_CSS_TEMPLATE = """
<style>
    :root {
        color-scheme: light !important;
        --primary-color: __PRIMARY_COLOR__;
        --background-color: __BACKGROUND_COLOR__;
        --secondary-background-color: __SECONDARY_BACKGROUND_COLOR__;
        --text-color: __TEXT_COLOR__;
        --font: "Source Sans", "Source Sans Pro", sans-serif;
    }

    @media (prefers-color-scheme: dark) {
        :root {
            color-scheme: light !important;
        }
    }

    html,
    body,
    [data-testid="stAppViewContainer"],
    [data-testid="stApp"],
    .stApp {
        background-color: __BACKGROUND_COLOR__ !important;
        color: __TEXT_COLOR__ !important;
        font-family: "Source Sans", "Source Sans Pro", sans-serif !important;
    }

    .stApp [data-testid="stSidebar"] {
        background-color: __SECONDARY_BACKGROUND_COLOR__ !important;
        color: __TEXT_COLOR__ !important;
    }

    .stApp [data-testid="stHeader"] {
        background-color: rgba(255, 255, 255, 0.96) !important;
    }

    .stApp [data-testid="stSidebar"] label,
    .stApp [data-testid="stWidgetLabel"],
    .stApp [data-testid="stMarkdownContainer"] p,
    .stApp [data-testid="stMarkdownContainer"] li,
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        color: __TEXT_COLOR__ !important;
    }

    .stApp button,
    .stApp [data-baseweb="button"] {
        color: __TEXT_COLOR__;
        background-color: __BACKGROUND_COLOR__;
        border-color: #d1d5db;
    }

    .stApp button[kind="primary"],
    .stApp [data-baseweb="button"][kind="primary"] {
        background-color: __PRIMARY_COLOR__ !important;
        border-color: __PRIMARY_COLOR__ !important;
        color: #ffffff !important;
    }

    .stApp input,
    .stApp textarea,
    .stApp [data-baseweb="input"] input,
    .stApp [data-baseweb="textarea"] textarea,
    .stApp [data-baseweb="select"] > div {
        background-color: __BACKGROUND_COLOR__ !important;
        color: __TEXT_COLOR__ !important;
        border-color: #d1d5db !important;
    }

    .stApp [data-testid="stDataFrame"],
    .stApp [data-testid="stDataEditor"] {
        background-color: __BACKGROUND_COLOR__ !important;
        color: __TEXT_COLOR__ !important;
    }

    .stApp [data-testid="stExpander"] summary {
        color: __TEXT_COLOR__ !important;
    }

    /* st.iframe forbids height=0; collapse the 1px theme-bootstrap iframe. */
    [data-testid="stIFrame"]:has(iframe[height="1"]),
    [data-testid="stIFrame"]:has(iframe[height="1px"]) {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        border: 0 !important;
        overflow: hidden !important;
    }
</style>
"""


def _build_force_light_css() -> str:
    return (
        _FORCE_LIGHT_CSS_TEMPLATE.replace("__PRIMARY_COLOR__", PBA_THEME["primaryColor"])
        .replace("__BACKGROUND_COLOR__", PBA_THEME["backgroundColor"])
        .replace("__SECONDARY_BACKGROUND_COLOR__", PBA_THEME["secondaryBackgroundColor"])
        .replace("__TEXT_COLOR__", PBA_THEME["textColor"])
    )


FORCE_LIGHT_CSS: str = _build_force_light_css()


def _build_theme_bootstrap_html() -> str:
    theme_payload = {
        "name": PBA_THEME_NAME,
        "themeInput": dict(PBA_THEME),
    }
    theme_value_json = json.dumps(theme_payload)
    known_paths_json = json.dumps(KNOWN_APP_PATHS)
    cache_version = STREAMLIT_THEME_CACHE_VERSION

    return f"""
<script>
(function () {{
    const themeValue = {json.dumps(theme_value_json)};
    const knownPaths = {known_paths_json};
    const cacheVersion = {cache_version};

    function parentWindow() {{
        try {{
            return window.parent && window.parent !== window ? window.parent : window;
        }} catch (err) {{
            return window;
        }}
    }}

    const parent = parentWindow();
    const parentDocument = parent.document;
    const currentPath = parent.location.pathname || "/";
    const currentThemeKey = "stActiveTheme-" + currentPath + "-v" + cacheVersion;
    const reloadKey = "pba-theme-bootstrap-reloaded:" + currentPath;

    function themeKeyForPath(path) {{
        return "stActiveTheme-" + path + "-v" + cacheVersion;
    }}

    function addOverlay() {{
        if (parentDocument.getElementById("pba-theme-bootstrap-overlay")) {{
            return;
        }}

        const style = parentDocument.createElement("style");
        style.id = "pba-theme-bootstrap-style";
        style.textContent = `
            #pba-theme-bootstrap-overlay {{
                position: fixed;
                inset: 0;
                z-index: 2147483647;
                display: flex;
                align-items: center;
                justify-content: center;
                background: #ffffff;
                color: #111827;
                font: 600 1.05rem "Source Sans", "Source Sans Pro", sans-serif;
            }}
            #pba-theme-bootstrap-overlay .pba-loader {{
                width: min(340px, 62vw);
                text-align: center;
            }}
            #pba-theme-bootstrap-overlay .pba-bar {{
                height: 4px;
                margin-top: 18px;
                overflow: hidden;
                border-radius: 999px;
                background: #dbeafe;
            }}
            #pba-theme-bootstrap-overlay .pba-bar::before {{
                content: "";
                display: block;
                height: 100%;
                width: 42%;
                border-radius: inherit;
                background: linear-gradient(90deg, #2563eb, #60a5fa);
                animation: pba-loader-slide 1.05s ease-in-out infinite;
            }}
            @keyframes pba-loader-slide {{
                0% {{ transform: translateX(-110%); }}
                50% {{ transform: translateX(70%); }}
                100% {{ transform: translateX(260%); }}
            }}
        `;

        const overlay = parentDocument.createElement("div");
        overlay.id = "pba-theme-bootstrap-overlay";
        overlay.innerHTML = `
            <div class="pba-loader">
                <div>Loading pricing analysis...</div>
                <div class="pba-bar"></div>
            </div>
        `;

        parentDocument.head.appendChild(style);
        parentDocument.body.appendChild(overlay);
    }}

    function removeOverlay() {{
        const overlay = parentDocument.getElementById("pba-theme-bootstrap-overlay");
        if (overlay) {{
            overlay.remove();
        }}
        const style = parentDocument.getElementById("pba-theme-bootstrap-style");
        if (style) {{
            style.remove();
        }}
    }}

    function seedTheme() {{
        let changed = false;
        const keys = new Set(knownPaths.map(themeKeyForPath));
        keys.add(currentThemeKey);

        for (const key of keys) {{
            if (parent.localStorage.getItem(key) !== themeValue) {{
                parent.localStorage.setItem(key, themeValue);
                changed = true;
            }}
        }}
        return changed;
    }}

    function isWhiteish(color) {{
        if (!color) {{
            return false;
        }}
        const normalized = String(color).replace(/\\s/g, "").toLowerCase();
        return normalized === "rgb(255,255,255)"
            || normalized === "#ffffff"
            || normalized === "#fff"
            || normalized === "white";
    }}

    function isThemed() {{
        const app = parentDocument.querySelector(".stApp");
        if (!app) {{
            return false;
        }}

        if (parent.localStorage.getItem(currentThemeKey) !== themeValue) {{
            return false;
        }}

        const appStyle = parent.getComputedStyle(app);
        if (!isWhiteish(appStyle.backgroundColor)) {{
            return false;
        }}

        const widget = app.querySelector(
            '[data-testid="stWidgetLabel"], [data-testid="stSidebar"], '
            + 'button, [data-baseweb="button"], input, textarea'
        );
        return Boolean(widget);
    }}

    function finishHydration() {{
        parent.sessionStorage.removeItem(reloadKey);
        removeOverlay();
    }}

    let finished = false;
    function tryFinish() {{
        if (finished) {{
            return;
        }}
        if (isThemed()) {{
            finished = true;
            finishHydration();
        }}
    }}

    addOverlay();
    const changed = seedTheme();
    const alreadyReloaded = parent.sessionStorage.getItem(reloadKey) === "1";

    if (changed && !alreadyReloaded) {{
        parent.sessionStorage.setItem(reloadKey, "1");
        parent.location.reload();
        return;
    }}

    const startedAt = Date.now();
    const maxWaitMs = 8000;

    const observer = new parent.MutationObserver(function () {{
        tryFinish();
    }});

    if (parentDocument.body) {{
        observer.observe(parentDocument.body, {{
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["class", "style"],
        }});
    }}

    const interval = parent.setInterval(function () {{
        tryFinish();
        if (finished || Date.now() - startedAt > maxWaitMs) {{
            parent.clearInterval(interval);
            observer.disconnect();
            if (!finished) {{
                finished = true;
                finishHydration();
            }}
        }}
    }}, 100);
}})();
</script>
"""


THEME_BOOTSTRAP_HTML: str = _build_theme_bootstrap_html()


def apply_page_theme() -> None:
    """Inject light-theme CSS and localStorage bootstrap on the current page."""
    import streamlit as st

    st.markdown(FORCE_LIGHT_CSS, unsafe_allow_html=True)
    # st.iframe rejects height=0 (must be >0, "stretch", or "content").
    if hasattr(st, "iframe"):
        st.iframe(THEME_BOOTSTRAP_HTML, height=1)
    else:
        from streamlit.components.v1 import html as component_html

        component_html(THEME_BOOTSTRAP_HTML, height=0)
