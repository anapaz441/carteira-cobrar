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

inicio = servico.inicio_do_ciclo(ciclo)
hoje = date.today()
st.caption(
    f"Carteira {ciclo['mes'][5:]}/{ciclo['mes'][:4]} · gerada em {ui.data_br(ciclo['gerado_em'])}"
    f" · contatos contados desde {ui.data_br(inicio)} · meta: {config.META_CONTATOS} "
    f"contatos por cliente · faixa {config.DIAS_ATRASO_MIN}–{config.DIAS_ATRASO_MAX} dias"
)

with st.spinner("Buscando títulos e ligações no SIAC..."):
    df = servico.painel(ciclo)
    contatos = servico.contatos_do_ciclo(ciclo)
    sugestao = servico.sugestao_novos(ciclo["id"])

if df.is_empty():
    st.warning("A carteira deste mês está vazia.")
    st.stop()

cob = servico.cobradores(somente_ativos=False)
nomes = dict(cob.select("cod_usuario", "nome").iter_rows())
resumo = progresso.resumo_por_cobrador(df, cob)
ritmo = progresso.ritmo_esperado(hoje, inicio)

# ---------------------------- cartões do topo ------------------------------
vl_ini = df["vl_faixa_ini"].sum()
recuperado = df["recuperado"].sum()
n = df.height
meta_total = n * config.META_CONTATOS
feitos = int(df["contatos"].clip(upper_bound=config.META_CONTATOS).sum())
prog = df["progresso"].mean()

c1, c2, c3 = st.columns(3)
c1.metric("Clientes na carteira", n)
c2.metric(
    "Em aberto na faixa hoje",
    ui.brl_curto(df["vl_faixa"].sum()),
    help="Títulos que HOJE estão com 16–60 dias de atraso nos clientes da carteira",
)
c3.metric(
    "Recuperado",
    ui.brl_curto(recuperado),
    f"{ui.pct(recuperado / vl_ini if vl_ini else 0)} do que estava na faixa",
    help="Quanto foi pago dos títulos que estavam na faixa quando o cliente entrou na carteira",
)
c4, c5, c6 = st.columns(3)
c4.metric(
    "Contatos (rumo à meta)",
    f"{feitos} / {meta_total}",
    help=f"Soma dos contatos por cliente, limitada a {config.META_CONTATOS} por cliente",
)
c5.metric("Progresso médio", ui.pct(prog), f"{(prog - ritmo) * 100:+.0f} p.p. vs esperado hoje")
c6.metric("🔴 Sem nenhum contato", int((df["status"] == progresso.STATUS_SEM_CONTATO).sum()))

# ---------------------- novos clientes na faixa -----------------------------
st.subheader("🆕 Clientes que entraram na faixa")
if sugestao.is_empty():
    st.success("Nenhum cliente novo fora da carteira. Todos já estão com um cobrador. 👍")
else:
    sugestao = sugestao.with_columns(
        pl.col("entrou_faixa_em").cast(pl.Date),
        pl.col("loja_principal")
        .replace_strict(config.LOJAS_PRIORIDADE, default="Outra", return_dtype=pl.Utf8)
        .alias("loja"),
    ).sort(["entrou_faixa_em", "vl_faixa"], descending=[True, True])
    de_hoje = sugestao.filter(pl.col("entrou_faixa_em") == hoje).height
    st.write(
        f"**{sugestao.height}** cliente(s) fora da carteira — **{de_hoje} entraram hoje**. "
        "O cobrador já vem sugerido pela regra de equilíbrio; troque se quiser e clique em "
        "**Atribuir**."
    )
    so_hoje = st.toggle("Mostrar só os que entraram hoje", value=de_hoje > 0)
    vis = sugestao.filter(pl.col("entrou_faixa_em") == hoje) if so_hoje else sugestao
    ativos = servico.cobradores()
    nomes_ativos = dict(ativos.select("cod_usuario", "nome").iter_rows())
    tabela = vis.select(
        pl.lit(True).alias("atribuir"),
        "codcli",
        "cliente",
        "loja",
        "entrou_faixa_em",
        "vl_faixa",
        "vl_vencido",
        "qt_titulos",
        pl.col("cod_usuario")
        .replace_strict(nomes_ativos, default=None, return_dtype=pl.Utf8)
        .alias("cobrador"),
    ).to_pandas()
    editado = st.data_editor(
        tabela,
        hide_index=True,
        width="stretch",
        disabled=[
            "codcli",
            "cliente",
            "loja",
            "entrou_faixa_em",
            "vl_faixa",
            "vl_vencido",
            "qt_titulos",
        ],
        column_config={
            "atribuir": st.column_config.CheckboxColumn("Atribuir?"),
            "codcli": "Código",
            "cliente": "Cliente",
            "loja": "Loja",
            "entrou_faixa_em": st.column_config.DateColumn("Entrou na faixa", format="DD/MM"),
            "vl_faixa": st.column_config.NumberColumn("Débito 16–60d (R$)", format="localized"),
            "vl_vencido": st.column_config.NumberColumn("Débito total (R$)", format="localized"),
            "qt_titulos": "Títulos",
            "cobrador": st.column_config.SelectboxColumn(
                "Cobrador", options=list(nomes_ativos.values()), required=True
            ),
        },
        key="editor_novos",
    )
    marcados = editado[editado["atribuir"]]
    if st.button(
        f"✅ Atribuir {len(marcados)} cliente(s)", type="primary", disabled=marcados.empty
    ):
        cod_por_nome = {v: k for k, v in nomes_ativos.items()}
        escolha = pl.DataFrame(
            {
                "codcli": marcados["codcli"].tolist(),
                "cod_escolhido": [cod_por_nome[n] for n in marcados["cobrador"].tolist()],
            }
        )
        salvar = (
            sugestao.join(escolha, on="codcli", how="inner")
            .with_columns(pl.col("cod_escolhido").alias("cod_usuario"))
            .drop("cod_escolhido")
        )
        qtd = servico.atribuir_novos(ciclo["id"], salvar)
        st.toast(f"{qtd} cliente(s) atribuído(s).", icon="✅")
        st.rerun()

# ---------------------------- por cobrador ---------------------------------
st.subheader("Por cobrador")
st.markdown(f"**% da meta de contatos, dia a dia (desde {inicio.strftime('%d/%m')})**")
serie, esperado = servico.progresso_diario(ciclo, df)
st.plotly_chart(ui.grafico_progresso_diario(serie, esperado), width="stretch")
st.dataframe(
    resumo.select(
        "nome",
        "tipo",
        "clientes",
        "vl_faixa_atual",
        "recuperado",
        "pct_recuperado",
        "contatos",
        "efetivos",
        "progresso",
        "sem_contato",
        "regularizados",
    ).to_pandas(),
    hide_index=True,
    width="stretch",
    column_config={
        "nome": "Cobrador",
        "tipo": "Tipo",
        "clientes": "Clientes",
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
st.subheader("Contatos registrados por dia")
if contatos.is_empty():
    st.info("Nenhuma ligação registrada no SIAC para esses clientes desde o início do ciclo.")
else:
    st.plotly_chart(
        ui.grafico_contatos_por_dia(contatos, inicio, min(hoje, progresso.fim_do_mes(inicio))),
        width="stretch",
    )

ui.rodape_atualizacao()
