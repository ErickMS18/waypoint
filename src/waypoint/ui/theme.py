"""Design tokens for the dark and light themes (validated chart palette + WCAG-friendly ink)."""
from __future__ import annotations

import altair as alt
import streamlit as st

# Chart palettes were checked with the dataviz validator (lightness band, chroma, CVD separation, contrast).
TOKENS = {
    "dark": {
        "base": "dark", "bg": "#121211", "surface": "#1a1a19", "surface2": "#232321", "ink": "#f0efec",
        "ink2": "#c3c2b7", "muted": "#9d9b94", "grid": "#2c2c2a", "axis": "#383835",
        "border": "rgba(255,255,255,0.10)", "primary": "#3987e5", "required": "#3987e5", "nice": "#d95926",
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"],
        "good": "#0ca30c", "warn": "#fab219", "bad": "#d03b3b", "on_primary": "#ffffff",
        "nav_active": "rgba(57,135,229,0.20)",
    },
    "light": {
        "base": "light", "bg": "#f6f5f1", "surface": "#fcfcfb", "surface2": "#efeee9", "ink": "#0b0b0b",
        "ink2": "#52514e", "muted": "#6b6a65", "grid": "#e1e0d9", "axis": "#c3c2b7",
        "border": "rgba(11,11,11,0.10)", "primary": "#2a78d6", "required": "#2a78d6", "nice": "#eb6834",
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
        "good": "#006300", "warn": "#9a6a00", "bad": "#b42323", "on_primary": "#ffffff",
        "nav_active": "rgba(42,120,214,0.13)",
    },
}

# identity colors (always shown together with an icon + label, never color alone)
AREA_SLOT = {"carreira": 0, "faculdade": 1, "estagio": 2, "pesquisa": 3, "interesses": 4, "pessoal": 5,
             "exploracao": 6, "estudo": 0}
ROLE_SLOT = {"ai_ml_engineer": 0, "data_scientist": 1, "bi_analyst": 2, "analytics_engineer": 6, "mlops_engineer": 4,
             "data_analyst": 5, "data_engineer": 7}

CURRENT = {"name": "dark"}


def tok() -> dict:
    return TOKENS[CURRENT["name"]]


def area_color(area: str) -> str:
    return tok()["series"][AREA_SLOT.get(area, 3)]


def role_color(rid: str, all_ids: list[str]) -> str:
    if rid in ROLE_SLOT:
        return tok()["series"][ROLE_SLOT[rid]]
    custom = [r for r in all_ids if r not in ROLE_SLOT]
    return tok()["series"][[3, 5, 7][custom.index(rid) % 3] if rid in custom else 3]


def apply_theme(name: str) -> bool:
    """Switch Streamlit's theme at runtime. Returns True when a rerun is needed."""
    name = name if name in TOKENS else "dark"
    CURRENT["name"] = name
    t = TOKENS[name]
    wanted = {"theme.base": t["base"], "theme.primaryColor": t["primary"], "theme.backgroundColor": t["bg"],
              "theme.secondaryBackgroundColor": t["surface2"], "theme.textColor": t["ink"]}
    changed = False
    for k, v in wanted.items():
        try:
            if st.get_option(k) != v:
                st._config.set_option(k, v)  # noqa: SLF001 — documented workaround for runtime theming
                changed = True
        except Exception:
            pass
    return changed


def inject_css() -> None:
    t = tok()
    st.markdown(f"""
<style>
  :root {{ --wp-surface:{t['surface']}; --wp-surface2:{t['surface2']}; --wp-ink:{t['ink']}; --wp-ink2:{t['ink2']};
          --wp-muted:{t['muted']}; --wp-border:{t['border']}; --wp-primary:{t['primary']}; }}
  .block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1240px; }}
  h1, h2, h3 {{ letter-spacing: -0.01em; }}
  /* cards: any container created with key="card_*" */
  [class*="st-key-card"] {{ background: var(--wp-surface); border: 1px solid var(--wp-border) !important;
                            border-radius: 14px; padding: 18px 20px 16px 20px; }}
  [class*="st-key-hero"] {{ background: var(--wp-surface); border: 1px solid var(--wp-border); border-left: 4px solid var(--wp-primary);
                            border-radius: 14px; padding: 22px 24px; }}
  .wp-eyebrow {{ text-transform: uppercase; letter-spacing: .08em; font-size: .72rem; font-weight: 600; color: var(--wp-ink2); margin-bottom: .25rem; }}
  .wp-h1 {{ font-size: 2rem; font-weight: 700; line-height: 1.2; margin: 0 0 .2rem 0; color: var(--wp-ink); }}
  .wp-sub {{ color: var(--wp-ink2); margin: 0 0 1.2rem 0; font-size: 1rem; }}
  .wp-now-title {{ font-size: 1.55rem; font-weight: 700; line-height: 1.25; margin: .15rem 0 .35rem 0; color: var(--wp-ink); }}
  .wp-meta {{ color: var(--wp-ink2); font-size: .92rem; }}
  .wp-pill {{ display:inline-block; padding: 2px 10px; margin: 2px 6px 2px 0; border-radius: 999px; font-size: .82rem;
             border: 1px solid var(--wp-border); color: var(--wp-ink); background: var(--wp-surface2); white-space: nowrap; }}
  .wp-dot {{ display:inline-block; width:.62rem; height:.62rem; border-radius: 3px; margin-right:.4rem; vertical-align: baseline; }}
  .wp-block {{ border: 1px solid var(--wp-border); border-radius: 10px; padding: 7px 10px; margin: 6px 0; background: var(--wp-surface2);
               font-size: .86rem; line-height: 1.3; color: var(--wp-ink); }}
  .wp-block .h {{ color: var(--wp-ink2); font-size: .78rem; }}
  .wp-block.done {{ opacity: .55; text-decoration: line-through; }}
  .wp-day {{ font-weight: 700; font-size: .95rem; color: var(--wp-ink); }}
  .wp-day.today {{ color: var(--wp-primary); }}
  .wp-muted {{ color: var(--wp-ink2); font-size: .88rem; }}
  .wp-bar {{ height: 6px; border-radius: 6px; background: var(--wp-surface2); overflow: hidden; margin: 4px 0 2px 0; }}
  .wp-bar > span {{ display:block; height: 100%; background: var(--wp-primary); border-radius: 6px; }}
  .wp-chip-due {{ font-size: .8rem; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--wp-border); color: var(--wp-ink2); }}
  .wp-chip-due.urgent {{ border-color: {t['bad']}; color: {t['ink']}; }}
  div[data-testid="stMetricValue"] {{ font-size: 1.65rem; }}
  /* sidebar navigation */
  [class*="st-key-nav_"] {{ margin-top: -11px; }}
  [class*="st-key-nav_"] button {{ justify-content: flex-start !important; padding: .42rem .75rem !important; border-radius: 9px !important;
                                   min-height: 2.25rem; border: 0 !important; color: var(--wp-ink) !important; }}
  [class*="st-key-nav_"] button > div {{ justify-content: flex-start !important; width: 100%; }}
  [class*="st-key-nav_"] button p {{ font-size: .95rem; }}
  [class*="st-key-nav_"] button[kind="tertiary"]:hover {{ background: var(--wp-surface2) !important; }}
  [class*="st-key-nav_"] button[kind="primary"] {{ background: {t['nav_active']} !important; box-shadow: inset 3px 0 0 var(--wp-primary); }}
  [class*="st-key-nav_"] button[kind="primary"] p {{ font-weight: 650; }}
  .wp-nav-section {{ text-transform: uppercase; letter-spacing: .08em; font-size: .7rem; font-weight: 700; color: var(--wp-ink2);
                     margin: 1rem 0 14px .2rem; }}
  .wp-brand {{ font-size: 1.25rem; font-weight: 800; color: var(--wp-ink); margin: 0; }}
  /* keyboard focus must always be visible (WCAG 2.4.7) */
  button:focus-visible, [role="tab"]:focus-visible, input:focus-visible {{ outline: 2px solid var(--wp-primary) !important; outline-offset: 2px; }}
</style>
""", unsafe_allow_html=True)


def style(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    t = tok()
    return (chart.configure(background="transparent", font="Source Sans Pro, sans-serif")
            .configure_axis(labelColor=t["ink2"], titleColor=t["ink2"], gridColor=t["grid"], domainColor=t["axis"],
                            tickColor=t["axis"], labelFontSize=12, titleFontSize=12)
            .configure_view(strokeWidth=0)
            .configure_legend(labelColor=t["ink2"], titleColor=t["ink2"], orient="top", labelLimit=320, labelFontSize=12))
