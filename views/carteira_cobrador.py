"""Tela: carteira de UM cobrador.

- Cobrador logado: vê só a própria carteira (sem escolher outro).
- Gestor: escolhe qual cobrador quer ver.
"""

import polars as pl
import streamlit as st

import config
from domain import progresso, servico
from ui import componentes as ui
from ui import sessao
from ui.cliente import cartao_cliente

ciclo = ui.seletor_ciclo()

cob = servico.cobradores(somente_ativos=False)
nomes = dict(cob.select("cod_usuario", "nome").iter_rows())

if sessao.perfil() == sessao.PERFIL_COBRADOR:
    cod = sessao.cod_usuario()
    st.title(f"📞 Minha carteira — {nomes.get(cod, cod)}")
else:
    st.title("📞 Carteiras dos cobradores")

if ciclo is None:
    st.info("A carteira do mês ainda não foi gerada. Fale com a gestão da cobrança.")
    st.stop()

with st.spinner("Buscando os clientes no SIAC..."):
    df = servico.painel(ciclo)
if df.is_empty():
    st.warning("A carteira deste mês está vazia.")
    st.stop()

if sessao.perfil() != sessao.PERFIL_COBRADOR:
    com_cliente = [c for c in nomes if c in set(df["cod_usuario"].to_list())]
    cod = st.selectbox("Cobrador", com_cliente, format_func=nomes.get, key="cobrador_escolhido")

meus = df.filter(pl.col("cod_usuario") == cod)
if meus.is_empty():
    st.info("Nenhum cliente na sua carteira deste mês.")
    st.stop()

# ---------------------------- cartões --------------------------------------
faixa_ini = meus["vl_faixa_ini"].sum()
recuperado = meus["recuperado"].sum()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Meus clientes", meus.height)
c2.metric(
    "Em aberto na faixa",
    ui.brl_curto(meus["vl_faixa"].sum()),
    help="Soma dos títulos que HOJE estão com 16 a 60 dias de atraso nos seus clientes",
)
c3.metric(
    "Valor recuperado",
    ui.brl_curto(recuperado),
    help="Quanto já foi pago dos títulos que estavam na faixa quando o cliente entrou na carteira",
)
c4.metric(
    "% recuperado",
    ui.pct(recuperado / faixa_ini if faixa_ini else 0),
    help=f"Recuperado ÷ débito na faixa quando a carteira foi gerada ({ui.brl(faixa_ini)})",
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
busca = f3.text_input("Buscar cliente (nome ou código)")

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

# Ordem de trabalho: quem tem menos contato primeiro, loja mais crítica, maior débito na faixa
vis = vis.with_columns(
    pl.col("status")
    .replace_strict({s: i for i, s in enumerate(progresso.ORDEM_STATUS)}, return_dtype=pl.Int32)
    .alias("_ordem_status")
).sort(
    ["_ordem_status", "contatos", "prioridade", "vl_faixa"],
    descending=[False, False, False, True],
)

st.caption(f"{vis.height} de {meus.height} clientes · ordenados pelo que é mais urgente")

colunas = [
    "status",
    "loja",
    "cliente_rotulo",
    "barra",
    "efetivos",
    "telefones",
    "vl_faixa",
    "vl_vencido",
    "qt_titulos",
    "dias_atraso_max",
    "ult_contato",
    "ult_resultado",
    "ult_texto",
]
# Contatos em "x de 6". Regularizado aparece cheio (não precisa mais ligar).
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
    height=min(38 * (tabela.height + 1) + 4, 600),
    column_config={
        "status": st.column_config.TextColumn("Situação", pinned=True),
        "loja": "Loja",
        "cliente_rotulo": st.column_config.TextColumn("Cliente", pinned=True, width="medium"),
        "barra": st.column_config.ProgressColumn(
            f"Contatos (mín. {config.META_CONTATOS})",
            min_value=0,
            max_value=config.META_CONTATOS,
            format=f"%d de {config.META_CONTATOS}",
        ),
        "efetivos": st.column_config.NumberColumn(
            "Efetivos",
            help="Contatos em que falou com o cliente (ligação ou WhatsApp). "
            "Sem retorno / não atende não contam aqui.",
        ),
        "telefones": st.column_config.TextColumn("Telefones", width="medium"),
        "vl_faixa": st.column_config.NumberColumn("Débito 16–60d (R$)", format="localized"),
        "vl_vencido": st.column_config.NumberColumn("Débito total (R$)", format="localized"),
        "qt_titulos": "Qtd títulos",
        "dias_atraso_max": "Dias atraso (máx.)",
        "ult_contato": "Último contato · quem",
        "ult_resultado": "Resultado",
        "ult_texto": st.column_config.TextColumn("Anotação", width="large"),
    },
)
st.caption(
    "Contatos = ligações registradas no SIAC + contatos registrados aqui (efetivos e sem "
    "retorno; máx. 1 por dia por cliente). Efetivos = falou com o cliente. "
    f"O que é registrado no SIAC aparece em até {config.TTL_CONTATOS // 60} min."
)

# ---------------------------- rotina do dia --------------------------------
st.divider()
st.subheader("🗓️ Rotina do dia")
st.caption(
    "Monta a lista de quem ligar hoje: primeiro quem ainda não teve contato, depois quem está "
    "há mais tempo sem contato (loja mais crítica e maior débito desempatam). "
    "Quem já teve contato hoje e quem já pagou tudo ficam de fora."
)
r1, r2 = st.columns([1, 3])
tamanho = r1.number_input(
    "Quantos clientes", min_value=1, max_value=60, value=config.ROTINA_TAMANHO_PADRAO
)
r2.write("")
r2.write("")
gerar = r2.button("⚡ Gerar rotina", type="primary")

lista = servico.rotina(ciclo, cod, meus, gerar=gerar, tamanho=int(tamanho))
if not lista:
    st.info("Nenhuma rotina gerada hoje. Clique em **Gerar rotina**.")
else:
    feitos = servico.contatados_hoje(ciclo)
    por_cod = {r["codcli"]: r for r in meus.iter_rows(named=True)}
    lista = [c for c in lista if c in por_cod]
    st.progress(
        sum(c in feitos for c in lista) / len(lista),
        text=f"Rotina de hoje: {sum(c in feitos for c in lista)} de {len(lista)} com contato hoje",
    )
    autor = sessao.cod_usuario()
    for i, codcli in enumerate(lista, start=1):
        cli = por_cod[codcli]
        marca = "✅" if codcli in feitos else "⬜"
        titulo = (
            f"{marca} {i}. {codcli} · {cli.get('cliente') or ''} — {cli['loja']} · "
            f"{ui.brl(cli['vl_faixa'])} na faixa · {cli['contatos']}/{config.META_CONTATOS} contatos"
        )
        with st.expander(titulo, expanded=False):
            cartao_cliente(cli, autor, chave=f"rot_{codcli}")

# ---------------------------- qualquer cliente -----------------------------
st.divider()
st.subheader("✍️ Anotar em qualquer cliente da carteira")
rotulos = dict(meus.select("codcli", "cliente_rotulo").iter_rows())
escolhido = st.selectbox(
    "Cliente",
    sorted(rotulos),
    format_func=rotulos.get,
    index=None,
    placeholder="Busque pelo código ou nome",
)
if escolhido:
    cli = next(r for r in meus.iter_rows(named=True) if r["codcli"] == escolhido)
    with st.container(border=True, key="cartao_avulso"):
        cartao_cliente(cli, sessao.cod_usuario(), chave=f"avulso_{escolhido}")

ui.rodape_atualizacao()
