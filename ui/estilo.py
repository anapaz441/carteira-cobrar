"""Visual do app: cor de destaque, cards com borda e sombra.

A cor principal também está em .streamlit/config.toml (primaryColor).
Para mudar a identidade visual, mude as constantes abaixo.
"""

import streamlit as st

COR_DESTAQUE = "#00A5AC"
COR_DESTAQUE_ESCURA = "#007F85"
COR_DESTAQUE_CLARA = "#E6F6F7"
COR_BORDA = "#E3E8EC"
SOMBRA = "0 2px 6px rgba(16, 42, 67, 0.06), 0 8px 24px rgba(16, 42, 67, 0.06)"

_CSS = f"""
<style>
/* Fundo levemente acinzentado para os cards brancos se destacarem */
[data-testid="stAppViewContainer"] {{ background: #F6F8FA; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.2rem; max-width: 1400px; }}

/* Títulos */
h1 {{ font-weight: 700 !important; letter-spacing: -0.02em; color: #102A43; }}
h2, h3 {{ color: #102A43; letter-spacing: -0.01em; }}
h1::after {{
    content: ""; display: block; width: 56px; height: 4px; margin-top: 10px;
    border-radius: 4px; background: {COR_DESTAQUE};
}}

/* Cards de número (st.metric) */
[data-testid="stMetric"] {{
    background: #FFFFFF;
    border: 1px solid {COR_BORDA};
    border-left: 5px solid {COR_DESTAQUE};
    border-radius: 14px;
    padding: 16px 20px 14px 20px;
    min-height: 132px;
    box-shadow: {SOMBRA};
}}
[data-testid="stMetricLabel"] p {{
    color: #52606D; font-size: 0.85rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em;
}}
[data-testid="stMetricValue"] {{ color: #102A43; font-weight: 700; }}

/* Tabelas */
[data-testid="stDataFrame"] {{
    background: #FFFFFF;
    border: 1px solid {COR_BORDA};
    border-radius: 14px;
    box-shadow: {SOMBRA};
    padding: 6px;
}}

/* Cartões de cliente (expanders da rotina), formulários e containers com borda */
[data-testid="stExpander"] details {{
    background: #FFFFFF;
    border: 1px solid {COR_BORDA} !important;
    border-radius: 14px !important;
    box-shadow: {SOMBRA};
}}
[data-testid="stExpander"] details summary:hover {{ color: {COR_DESTAQUE_ESCURA}; }}
[data-testid="stForm"] {{
    background: {COR_DESTAQUE_CLARA};
    border: 1px solid #BFE6E8 !important;
    border-radius: 14px !important;
}}
/* Containers com borda que recebem key "cartao_*" (login, cartão de cliente) */
[class*="st-key-cartao"] {{
    background: #FFFFFF;
    border: 1px solid {COR_BORDA} !important;
    border-radius: 16px !important;
    box-shadow: {SOMBRA};
    padding: 20px 24px !important;
}}
.st-key-cartao_login {{ margin-top: 6vh; border-top: 5px solid {COR_DESTAQUE} !important; }}
.st-key-cartao_login h1 {{ font-size: 2rem; }}

/* Gráficos */
[data-testid="stPlotlyChart"] {{
    background: #FFFFFF;
    border: 1px solid {COR_BORDA};
    border-radius: 14px;
    box-shadow: {SOMBRA};
    padding: 8px;
}}

/* Botões */
.stButton > button, .stFormSubmitButton > button {{
    border-radius: 10px; font-weight: 600; transition: all .15s ease;
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
    box-shadow: 0 4px 12px rgba(0, 165, 172, 0.30);
}}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {{
    background: {COR_DESTAQUE_ESCURA}; border-color: {COR_DESTAQUE_ESCURA};
}}

/* Avisos e barra lateral */
[data-testid="stAlert"] {{ border-radius: 12px; }}
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid {COR_BORDA}; }}
hr {{ border-color: {COR_BORDA} !important; }}
</style>
"""


def aplicar() -> None:
    """Injeta o CSS do app (chamar uma vez no app.py)."""
    st.markdown(_CSS, unsafe_allow_html=True)
