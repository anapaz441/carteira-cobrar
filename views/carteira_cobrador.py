"""Tela: Carteira do cobrador — os clientes dele, com o progresso de contatos."""

from datetime import date

import polars as pl
import streamlit as st

import config
from domain import progresso, servico
from ui import componentes as ui

st.title("📞 Minha carteira")

ciclo = ui.seletor_ciclo()
if ciclo is None:
    st.info("A carteira do mês ainda não foi gerada. Fale com a gestão da cobrança.")
    st.stop()

with st.spinner("Buscando seus clientes no SIAC..."):
    df = servico.painel(ciclo)
if df.is_empty():
    st.warning("A carteira deste mês está vazia.")
    st.stop()

cob = servico.cobradores(somente_ativos=False)
cobs_com_cliente = cob.filter(pl.col("cod_usuario").is_in(df["cod_usuario"].unique().to_list()))
nomes = dict(cobs_com_cliente.select("cod_usuario", "nome").iter_rows())

# Lembra a escolha do cobrador (por usuário/navegador, via session_state)
cod = st.selectbox("Cobrador", list(nomes), format_func=nomes.get, key="cobrador_escolhido")
meus = df.filter(pl.col("cod_usuario") == cod)

inicio = date.fromisoformat(ciclo["inicio"])
ritmo = progresso.ritmo_esperado(date.today(), inicio)
esperado_hoje = round(ritmo * config.META_CONTATOS, 1)

# ---------------------------- cartões --------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Meus clientes", meus.height)
c2.metric("Débito em aberto hoje", ui.brl_curto(meus["vl_vencido"].sum()))
c3.metric("Já recuperado", ui.brl_curto(meus["recuperado"].sum()))
c4.metric(
    "Progresso da meta",
    ui.pct(meus["progresso"].mean()),
    f"esperado hoje: {ui.pct(ritmo)}",
)

st.progress(
    float(meus["progresso"].mean()),
    text=(
        f"Meta: {config.META_CONTATOS} contatos por cliente até o fim do mês · "
        f"hoje o ideal é cada cliente já ter ~{esperado_hoje:g} contato(s)".replace(".", ",")
    ),
)

# ---------------------------- filtros --------------------------------------
f1, f2, f3 = st.columns([2, 2, 3])
status_sel = f1.multiselect(
    "Situação",
    progresso.ORDEM_STATUS,
    default=[progresso.STATUS_SEM_CONTATO, progresso.STATUS_ANDAMENTO],
    placeholder="Todas",
)
lojas_disp = [lj for lj in config.LOJAS_PRIORIDADE.values() if lj in meus["loja"].to_list()]
lojas_sel = f2.multiselect("Loja", lojas_disp, placeholder="Todas as lojas")
busca = f3.text_input("Buscar cliente (nome, fantasia ou código)")

vis = meus
if status_sel:
    vis = vis.filter(pl.col("status").is_in(status_sel))
if lojas_sel:
    vis = vis.filter(pl.col("loja").is_in(lojas_sel))
if busca:
    b = busca.strip().upper()
    vis = vis.filter(
        pl.col("codcli").str.to_uppercase().str.contains(b, literal=True)
        | pl.col("cliente").fill_null("").str.to_uppercase().str.contains(b, literal=True)
        | pl.col("fantasia").fill_null("").str.to_uppercase().str.contains(b, literal=True)
    )

# Ordem de trabalho: quem tem menos contato primeiro, loja mais crítica, maior débito
vis = vis.with_columns(
    pl.col("status")
    .replace_strict({s: i for i, s in enumerate(progresso.ORDEM_STATUS)}, return_dtype=pl.Int32)
    .alias("_ordem_status")
).sort(
    ["_ordem_status", "contatos", "prioridade", "vl_vencido"],
    descending=[False, False, False, True],
)

st.caption(f"{vis.height} de {meus.height} clientes · ordenados pelo que é mais urgente")

colunas = [
    "status",
    "barra",
    "efetivos",
    "fantasia",
    "cliente",
    "whatsapp",
    "telefone",
    "prioridade",
    "loja",
    "codcli",
    "vl_vencido",
    "vl_faixa",
    "qt_titulos",
    "dias_atraso_max",
    "ult_data",
    "ult_quem",
    "ult_resultado",
    "prox_ligacao",
    "ult_texto",
]
# Barra de progresso em "contatos / 6". Regularizado aparece cheio (não precisa mais ligar).
tabela = vis.with_columns(
    pl.when(pl.col("status") == progresso.STATUS_REGULARIZADO)
    .then(config.META_CONTATOS)
    .otherwise(pl.col("contatos").clip(upper_bound=config.META_CONTATOS))
    .alias("barra")
).select(colunas)

st.dataframe(
    tabela.to_pandas(),
    hide_index=True,
    width="stretch",
    height=min(38 * (tabela.height + 1) + 4, 640),
    column_config={
        "status": st.column_config.TextColumn(config.COLUNAS_PT["status"], pinned=True),
        "barra": st.column_config.ProgressColumn(
            f"Contatos (meta {config.META_CONTATOS})",
            min_value=0,
            max_value=config.META_CONTATOS,
            format=f"%d de {config.META_CONTATOS}",
            pinned=True,
        ),
        "efetivos": st.column_config.NumberColumn(
            config.COLUNAS_PT["efetivos"],
            help="Contatos em que falou com alguém (exclui não atende, ocupado, "
            "número errado, responsável ausente/ocupado)",
        ),
        "fantasia": st.column_config.TextColumn(config.COLUNAS_PT["fantasia"], pinned=True),
        "cliente": config.COLUNAS_PT["cliente"],
        "whatsapp": config.COLUNAS_PT["whatsapp"],
        "telefone": config.COLUNAS_PT["telefone"],
        "prioridade": config.COLUNAS_PT["prioridade"],
        "loja": config.COLUNAS_PT["loja"],
        "codcli": config.COLUNAS_PT["codcli"],
        "vl_vencido": st.column_config.NumberColumn(
            config.COLUNAS_PT["vl_vencido"], format="localized"
        ),
        "vl_faixa": st.column_config.NumberColumn(
            config.COLUNAS_PT["vl_faixa"], format="localized"
        ),
        "qt_titulos": config.COLUNAS_PT["qt_titulos"],
        "dias_atraso_max": config.COLUNAS_PT["dias_atraso_max"],
        "ult_data": st.column_config.DateColumn(config.COLUNAS_PT["ult_data"], format="DD/MM/YYYY"),
        "ult_quem": config.COLUNAS_PT["ult_quem"],
        "ult_resultado": config.COLUNAS_PT["ult_resultado"],
        "prox_ligacao": st.column_config.DateColumn(
            config.COLUNAS_PT["prox_ligacao"], format="DD/MM/YYYY"
        ),
        "ult_texto": st.column_config.TextColumn(config.COLUNAS_PT["ult_texto"], width="large"),
    },
)
st.caption(
    "Os contatos vêm das ligações registradas na **cobrança do SIAC** "
    f"(máx. 1 por dia por cliente). Registrou agora? Aparece aqui em até {config.TTL_CONTATOS // 60} min."
)

# ---------------------------- histórico ------------------------------------
st.subheader("Histórico de um cliente")
opcoes = sorted(meus["codcli"].to_list())  # lista estável (não muda com os filtros)
rotulos = dict(
    meus.select(
        "codcli",
        (
            pl.col("codcli") + " · " + pl.col("fantasia").fill_null(pl.col("cliente")).fill_null("")
        ).alias("rotulo"),
    ).iter_rows()
)
escolhido = st.selectbox(
    "Cliente",
    opcoes,
    format_func=rotulos.get,
    index=None,
    placeholder="Escolha um cliente para ver as ligações",
)
if escolhido:
    hist = servico.historico(escolhido)
    if hist.is_empty():
        st.info("Nenhuma ligação registrada nos últimos 120 dias.")
    else:
        nomes_todos = dict(cob.select("cod_usuario", "nome").iter_rows())
        hist = hist.with_columns(
            pl.col("cd_usuario")
            .replace_strict(nomes_todos, default=None, return_dtype=pl.Utf8)
            .fill_null(pl.col("cd_usuario"))
            .alias("quem")
        )
        st.dataframe(
            hist.select(
                "data",
                "hora",
                "quem",
                "loja",
                "resultado",
                "anotacao",
                "valor_cobrado",
                "prox_ligacao",
            ).to_pandas(),
            hide_index=True,
            width="stretch",
            column_config={
                "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "hora": "Hora",
                "quem": "Quem falou",
                "loja": "Loja",
                "resultado": "Resultado",
                "anotacao": st.column_config.TextColumn("Anotação", width="large"),
                "valor_cobrado": st.column_config.NumberColumn(
                    "Valor cobrado (R$)", format="localized"
                ),
                "prox_ligacao": st.column_config.DateColumn("Próx. ligação", format="DD/MM/YYYY"),
            },
        )

ui.rodape_atualizacao()
