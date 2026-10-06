"""Componentes de tela reutilizáveis (formatação, seletor de ciclo, gráficos)."""

from datetime import date, datetime

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from data import carteira_store as store

COR_SERIE = "#2a78d6"  # cor única das barras (uma série só, sem legenda)
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


def grafico_progresso_cobradores(resumo: pl.DataFrame, ritmo: float) -> go.Figure:
    """Barra horizontal: % da meta de contatos por cobrador + linha do ritmo esperado."""
    d = resumo.sort("progresso")
    fig = go.Figure(
        go.Bar(
            x=d["progresso"].to_list(),
            y=d["nome"].to_list(),
            orientation="h",
            marker={"color": COR_SERIE, "cornerradius": 4},
            text=[pct(v) for v in d["progresso"].to_list()],
            textposition="outside",
            hovertemplate="%{y}: %{x:.0%} da meta<extra></extra>",
        )
    )
    fig.add_vline(
        x=ritmo,
        line_dash="dash",
        line_color=COR_TINTA_SEC,
        line_width=1.5,
        annotation_text=f"esperado hoje: {pct(ritmo)}",
        annotation_position="top",
    )
    fig.update_layout(
        height=60 + 42 * d.height,
        margin={"l": 10, "r": 30, "t": 30, "b": 10},
        xaxis={"range": [0, 1.12], "tickformat": ".0%", "gridcolor": "#ececea"},
        yaxis={"title": None},
        plot_bgcolor="rgba(0,0,0,0)",
        bargap=0.35,
    )
    return fig


def grafico_contatos_por_dia(contatos: pl.DataFrame, inicio: date) -> go.Figure:
    """Ligações registradas por dia no ciclo (todos os cobradores)."""
    por_dia = (
        contatos.filter(pl.col("dt_cobran") >= inicio).group_by("dt_cobran").len().sort("dt_cobran")
    )
    fig = go.Figure(
        go.Bar(
            x=por_dia["dt_cobran"].to_list(),
            y=por_dia["len"].to_list(),
            marker={"color": COR_SERIE, "cornerradius": 4},
            hovertemplate="%{x|%d/%m}: %{y} ligações<extra></extra>",
        )
    )
    fig.update_layout(
        height=260,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        xaxis={"tickformat": "%d/%m"},
        yaxis={"title": None, "gridcolor": "#ececea"},
        plot_bgcolor="rgba(0,0,0,0)",
        bargap=0.25,
    )
    return fig
