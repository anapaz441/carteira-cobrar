"""Componentes de tela reutilizáveis (formatação, seletor de ciclo, gráficos)."""

from datetime import date, datetime

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from data import carteira_store as store

COR_SERIE = "#00A5AC"  # cor única das barras (uma série só, sem legenda)
COR_TINTA_SEC = "#52514e"


def brl(valor: float | None, markdown: bool = True) -> str:
    """Formata em reais: 12345.6 → R$ 12.345,60.
    Em texto com markdown o "$" é escapado (senão o Streamlit entende como fórmula)."""
    if valor is None:
        return "—"
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R\\$ {s}" if markdown else f"R$ {s}"


def brl_curto(valor: float) -> str:
    """R$ 1,2 mi / R$ 345 mil — para os cartões do topo."""
    if abs(valor) >= 1_000_000:
        return f"R$ {valor / 1_000_000:,.2f} mi".replace(".", ",")
    if abs(valor) >= 1_000:
        return f"R$ {valor / 1_000:,.0f} mil".replace(",", ".")
    return brl(valor, markdown=False)


def pct(v: float) -> str:
    return f"{v * 100:.0f}%".replace(".", ",")


def data_br(d) -> str:
    if d is None or d == "":
        return "—"
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    return d.strftime("%d/%m/%Y")


def seletor_ciclo() -> dict | None:
    """Escolhe o mês da carteira (padrão: o mais recente). Fica na barra lateral."""
    ciclos = store.listar_ciclos()
    if ciclos.empty:
        return None
    meses = ciclos["mes"].tolist()
    rotulo = {m: f"{m[5:]}/{m[:4]}" for m in meses}
    mes = st.sidebar.selectbox("Carteira do mês", meses, format_func=rotulo.get, key="ciclo_mes")
    return store.obter_ciclo(mes)


def rodape_atualizacao() -> None:
    st.caption(
        f"Dados do SIAC atualizados a cada 2–5 min · última leitura "
        f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )


# Paleta categórica validada (ordem fixa; a cor segue o cobrador, não a posição)
PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

_LAYOUT_BASE = {
    "margin": {"l": 10, "r": 10, "t": 10, "b": 10},
    "plot_bgcolor": "rgba(0,0,0,0)",
    "paper_bgcolor": "rgba(0,0,0,0)",
    "hovermode": "x unified",
    "font": {"color": "#334E68"},
}


def _eixo_dias(fig: go.Figure) -> None:
    fig.update_xaxes(tickformat="%d/%m", dtick=86400000, showgrid=False, ticks="outside")


def grafico_progresso_diario(serie: pl.DataFrame, esperado: pl.DataFrame) -> go.Figure:
    """Linha por cobrador: % da meta de contatos acumulada dia a dia + linha do esperado."""
    fig = go.Figure()
    nomes = sorted(serie["nome"].unique().to_list())
    for i, nome in enumerate(nomes):
        d = serie.filter(pl.col("nome") == nome).sort("dia")
        fig.add_trace(
            go.Scatter(
                x=d["dia"].to_list(),
                y=d["progresso"].to_list(),
                name=nome,
                mode="lines+markers",
                line={"width": 2, "color": PALETA[i % len(PALETA)]},
                marker={"size": 7},
                hovertemplate=f"{nome}: %{{y:.0%}}<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=esperado["dia"].to_list(),
            y=esperado["esperado"].to_list(),
            name="Esperado",
            mode="lines",
            line={"width": 2, "color": COR_TINTA_SEC, "dash": "dash"},
            hovertemplate="Esperado: %{y:.0%}<extra></extra>",
        )
    )
    fig.update_layout(
        **_LAYOUT_BASE,
        height=340,
        yaxis={"tickformat": ".0%", "rangemode": "tozero", "gridcolor": "#ececea"},
        legend={"orientation": "h", "y": -0.18, "x": 0},
    )
    _eixo_dias(fig)
    return fig


def grafico_contatos_por_dia(contatos: pl.DataFrame, inicio: date, ate: date) -> go.Figure:
    """Contatos registrados por dia (SIAC + app), desde o dia 1 do mês. Dia sem contato = 0."""
    dias = pl.DataFrame(pl.date_range(inicio, ate, interval="1d", eager=True).alias("dt_cobran"))
    por_dia = (
        dias.join(contatos.group_by("dt_cobran").len(), on="dt_cobran", how="left")
        .with_columns(pl.col("len").fill_null(0))
        .sort("dt_cobran")
    )
    fig = go.Figure(
        go.Scatter(
            x=por_dia["dt_cobran"].to_list(),
            y=por_dia["len"].to_list(),
            mode="lines+markers",
            line={"width": 2, "color": COR_SERIE},
            marker={"size": 8},
            fill="tozeroy",
            fillcolor="rgba(0,165,172,0.08)",
            hovertemplate="%{x|%d/%m}: %{y} contatos<extra></extra>",
        )
    )
    fig.update_layout(
        **_LAYOUT_BASE,
        height=280,
        yaxis={"rangemode": "tozero", "gridcolor": "#ececea"},
        showlegend=False,
    )
    _eixo_dias(fig)
    return fig
