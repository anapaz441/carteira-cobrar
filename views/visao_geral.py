"""Tela: Visão geral (gestão) — como está a carteira do mês, por cobrador e por loja."""

from datetime import date

import polars as pl
import streamlit as st

import config
from domain import progresso, servico
from ui import componentes as ui
from ui import sessao

st.title("📊 Visão geral da cobrança")
sessao.exigir_gestor()

ciclo = ui.seletor_ciclo()
if ciclo is None:
    st.info("Ainda não existe carteira gerada. Vá em **Gerar carteira** para criar a do mês.")
    st.stop()

inicio = date.fromisoformat(ciclo["inicio"])
st.caption(
    f"Carteira {ciclo['mes'][5:]}/{ciclo['mes'][:4]} · gerada em {ui.data_br(ciclo['gerado_em'])}"
    f" · contatos contados desde {ui.data_br(inicio)} · meta: {config.META_CONTATOS} "
    f"contatos por cliente · faixa {config.DIAS_ATRASO_MIN}–{config.DIAS_ATRASO_MAX} dias"
)

with st.spinner("Buscando títulos e ligações no SIAC..."):
    df = servico.painel(ciclo)
    contatos = servico.contatos_do_ciclo(ciclo)
    novos = servico.clientes_novos(ciclo["id"])

if df.is_empty():
    st.warning("A carteira deste mês está vazia.")
    st.stop()

cob = servico.cobradores(somente_ativos=False)
resumo = progresso.resumo_por_cobrador(df, cob)
ritmo = progresso.ritmo_esperado(date.today(), inicio)

# ---------------------------- cartões do topo ------------------------------
vl_ini = df["vl_faixa_ini"].sum()
vl_atual = df["vl_faixa"].sum()
recuperado = df["recuperado"].sum()
n = df.height
meta_total = n * config.META_CONTATOS
feitos = int(df["contatos"].clip(upper_bound=config.META_CONTATOS).sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Clientes na carteira", n)
c2.metric(
    "Na faixa ao gerar",
    ui.brl_curto(vl_ini),
    help="Títulos de 16–60 dias quando cada cliente entrou na carteira",
)
c3.metric(
    "Em aberto na faixa hoje",
    ui.brl_curto(vl_atual),
    help="Títulos que HOJE estão com 16–60 dias de atraso nesses clientes",
)
c4.metric(
    "Recuperado",
    ui.brl_curto(recuperado),
    f"{ui.pct(recuperado / vl_ini if vl_ini else 0)} do que estava na faixa",
    help="Quanto foi pago dos títulos que estavam na faixa quando o cliente entrou na carteira",
)

c5, c6, c7, c8 = st.columns(4)
c5.metric(
    "Contatos (rumo à meta)",
    f"{feitos} / {meta_total}",
    help=f"Soma dos contatos por cliente, limitada a {config.META_CONTATOS} por cliente",
)
prog = df["progresso"].mean()
c6.metric(
    "Progresso médio",
    ui.pct(prog),
    f"{(prog - ritmo) * 100:+.0f} p.p. vs esperado hoje",
)
c7.metric("🔴 Sem nenhum contato", int((df["status"] == progresso.STATUS_SEM_CONTATO).sum()))
c8.metric(
    "✅ Meta atingida / regularizados",
    int(df["status"].is_in([progresso.STATUS_META, progresso.STATUS_REGULARIZADO]).sum()),
)

if novos.height:
    st.warning(
        f"**{novos.height} cliente(s) novo(s)** entraram na faixa de "
        f"{config.DIAS_ATRASO_MIN}–{config.DIAS_ATRASO_MAX} dias depois que a carteira foi "
        f"gerada ({ui.brl(novos['vl_faixa'].sum())} na faixa). "
        "Distribua em **Gerar carteira → Distribuir novos clientes**."
    )

# ---------------------------- por cobrador ---------------------------------
st.subheader("Por cobrador")
col_g, col_t = st.columns([2, 3])
with col_g:
    st.markdown("**% da meta de contatos**")
    st.plotly_chart(ui.grafico_progresso_cobradores(resumo, ritmo), width="stretch")
with col_t:
    st.dataframe(
        resumo.select(
            "nome",
            "tipo",
            "clientes",
            "vl_faixa_ini",
            "vl_faixa_atual",
            "recuperado",
            "pct_recuperado",
            "contatos",
            "efetivos",
            "progresso",
            "sem_contato",
            "meta_atingida",
            "regularizados",
        ).to_pandas(),
        hide_index=True,
        width="stretch",
        column_config={
            "nome": "Cobrador",
            "tipo": "Tipo",
            "clientes": "Clientes",
            "vl_faixa_ini": st.column_config.NumberColumn(
                "Na faixa ao gerar (R$)", format="localized"
            ),
            "vl_faixa_atual": st.column_config.NumberColumn(
                "Em aberto na faixa (R$)", format="localized"
            ),
            "recuperado": st.column_config.NumberColumn("Recuperado (R$)", format="localized"),
            "pct_recuperado": st.column_config.NumberColumn("% recup.", format="percent"),
            "contatos": "Contatos",
            "efetivos": "Efetivos",
            "progresso": st.column_config.ProgressColumn(
                "Meta", min_value=0, max_value=1, format="percent"
            ),
            "sem_contato": "Sem contato",
            "meta_atingida": "Meta ok",
            "regularizados": "Regularizados",
        },
    )

# ---------------------------- por loja -------------------------------------
st.subheader("Por loja (ordem de prioridade)")
por_loja = progresso.resumo_por_loja(df)
st.dataframe(
    por_loja.select(
        "prioridade",
        "loja",
        "clientes",
        "vl_faixa_ini",
        "vl_faixa_atual",
        "recuperado",
        "progresso",
        "sem_contato",
    ).to_pandas(),
    hide_index=True,
    width="stretch",
    column_config={
        "prioridade": "Prior.",
        "loja": "Loja",
        "clientes": "Clientes",
        "vl_faixa_ini": st.column_config.NumberColumn("Na faixa ao gerar (R$)", format="localized"),
        "vl_faixa_atual": st.column_config.NumberColumn(
            "Em aberto na faixa (R$)", format="localized"
        ),
        "recuperado": st.column_config.NumberColumn("Recuperado (R$)", format="localized"),
        "progresso": st.column_config.ProgressColumn(
            "Meta de contatos", min_value=0, max_value=1, format="percent"
        ),
        "sem_contato": "Sem contato",
    },
)

# Distribuição de clientes por loja x cobrador (para conferir o equilíbrio)
with st.expander("Quantos clientes de cada loja cada cobrador tem"):
    matriz = (
        df.group_by("loja", "cobrador")
        .len()
        .pivot(on="cobrador", index="loja", values="len")
        .fill_null(0)
    )
    ordem = {nome: i for i, nome in enumerate(config.LOJAS_PRIORIDADE.values())}
    matriz = (
        matriz.with_columns(
            pl.col("loja").replace_strict(ordem, default=99, return_dtype=pl.Int32).alias("_o")
        )
        .sort("_o")
        .drop("_o")
    )
    st.dataframe(matriz.to_pandas(), hide_index=True, width="stretch")

# ---------------------------- ritmo ----------------------------------------
st.subheader("Ligações registradas por dia")
if contatos.is_empty():
    st.info("Nenhuma ligação registrada no SIAC para esses clientes desde o início do ciclo.")
else:
    st.plotly_chart(ui.grafico_contatos_por_dia(contatos, inicio), width="stretch")

ui.rodape_atualizacao()
