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
from ui.simulador import calculadora_acordo

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

# ---------------------------- meus acordos ---------------------------------
acordos = servico.meus_acordos(cod, ciclo)
atrasados = acordos.filter(pl.col("atrasadas") > 0) if not acordos.is_empty() else acordos
if not atrasados.is_empty():
    st.error(
        f"⚠️ **{atrasados.height} acordo(s) com parcela atrasada** · "
        f"{ui.brl(atrasados['vl_atrasado'].sum())} em parcelas vencidas. "
        "Veja em **Meus acordos** abaixo e entre em contato hoje."
    )
titulo_acordos = f"🤝 Meus acordos ativos ({acordos.height})"
if not atrasados.is_empty():
    titulo_acordos += f" · ⚠️ {atrasados.height} com parcela atrasada"
with st.expander(titulo_acordos, expanded=not atrasados.is_empty()):
    if acordos.is_empty():
        st.info(
            "Nenhum acordo ativo dos seus clientes. (Entram os acordos dos clientes da sua "
            "carteira e os que você assinou de clientes que não estão na carteira de ninguém.)"
        )
    else:
        st.dataframe(
            acordos.with_columns(
                pl.when(pl.col("atrasadas") > 0)
                .then(pl.lit("⚠️ Atrasado"))
                .otherwise(pl.lit("✅ Em dia"))
                .alias("alerta"),
                (pl.col("codcli") + " · " + pl.col("cliente").fill_null("")).alias("cli"),
                pl.format("{}/{} pagas", pl.col("pagas"), pl.col("parcelas")).alias("andamento"),
                pl.col("cd_loja")
                .replace_strict(config.LOJAS_PRIORIDADE, default=None, return_dtype=pl.Utf8)
                .fill_null(pl.col("cd_loja"))
                .alias("loja"),
            )
            .select(
                "alerta",
                "cli",
                "loja",
                "dt_acordo",
                "vl_acordo",
                "vl_parcela",
                "andamento",
                "atrasadas",
                "vl_atrasado",
                "prox_vcto",
                "ult_contato",
                "ult_resultado",
            )
            .to_pandas(),
            hide_index=True,
            width="stretch",
            column_config={
                "alerta": st.column_config.TextColumn("Situação", pinned=True),
                "cli": st.column_config.TextColumn("Cliente", pinned=True, width="medium"),
                "loja": "Loja",
                "dt_acordo": st.column_config.DateColumn("Fechado em", format="DD/MM/YYYY"),
                "vl_acordo": st.column_config.NumberColumn(
                    "Valor do acordo (R$)", format="localized"
                ),
                "vl_parcela": st.column_config.NumberColumn("Parcela (R$)", format="localized"),
                "andamento": "Parcelas",
                "atrasadas": "Atrasadas",
                "vl_atrasado": st.column_config.NumberColumn("Em atraso (R$)", format="localized"),
                "prox_vcto": st.column_config.DateColumn("Próx. vencimento", format="DD/MM/YYYY"),
                "ult_contato": "Último contato · quem",
                "ult_resultado": "Resultado",
            },
        )
        st.caption(
            "Acordos ativos no SIAC (últimos 2 anos) dos seus clientes: os da sua carteira do "
            "mês e, fora da carteira, os que você assinou na observação. Cada cliente é de um "
            "cobrador só — mesmo com acordo em mais de uma loja."
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

# Contatos em "x de 6". Regularizado aparece cheio (não precisa mais ligar).
vis = vis.with_columns(
    pl.when(pl.col("status") == progresso.STATUS_REGULARIZADO)
    .then(config.META_CONTATOS)
    .otherwise(pl.col("contatos").clip(upper_bound=config.META_CONTATOS))
    .alias("barra")
)

_CONFIG_COMUM = {
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
    # colunas de acordo
    "acordo": "Acordo",
    "acordo_parcelas": "Parcelas",
    "vl_parcela": st.column_config.NumberColumn("Valor parcela (R$)", format="localized"),
    "atrasadas": st.column_config.NumberColumn(
        "Parcelas atrasadas", help="Parcelas do acordo vencidas e ainda não pagas"
    ),
    "prox_vcto": st.column_config.DateColumn("Próx. parcela", format="DD/MM/YYYY"),
}
_BASE = ["status", "loja", "cliente_rotulo", "barra", "efetivos", "telefones"]
_FIM = [
    "vl_faixa",
    "vl_vencido",
    "qt_titulos",
    "dias_atraso_max",
    "ult_contato",
    "ult_resultado",
    "ult_texto",
]


def _tabela(dados: pl.DataFrame, colunas: list[str]) -> None:
    if dados.is_empty():
        st.info("Nenhum cliente aqui com os filtros escolhidos.")
        return
    st.dataframe(
        dados.select(colunas).to_pandas(),
        hide_index=True,
        width="stretch",
        height=min(38 * (dados.height + 1) + 4, 520),
        column_config={c: _CONFIG_COMUM[c] for c in colunas},
    )


sem_acordo_ativo = vis.filter(~pl.col("acordo_ativo"))
com_acordo_ativo = vis.filter(pl.col("acordo_ativo"))

st.markdown(
    f"#### 📋 Sem acordo ou com acordo quebrado/inativo · {sem_acordo_ativo.height} cliente(s)"
)
st.caption("Prioridade da cobrança. Ordenados pelo que é mais urgente.")
_tabela(sem_acordo_ativo, [*_BASE[:3], "acordo", *_BASE[3:], *_FIM])

st.markdown(f"#### 🤝 Com acordo ativo · {com_acordo_ativo.height} cliente(s)")
st.caption(
    "Acompanhe as parcelas: quem tem parcela atrasada aparece primeiro e precisa de contato."
)
_tabela(
    com_acordo_ativo.sort(["atrasadas", "prox_vcto"], descending=[True, False], nulls_last=True),
    [*_BASE[:3], "acordo_parcelas", "vl_parcela", "atrasadas", "prox_vcto", *_BASE[3:], *_FIM],
)

st.caption(
    f"{vis.height} de {meus.height} clientes com os filtros escolhidos. "
    "Contatos = ligações registradas no SIAC + contatos registrados aqui (efetivos e sem "
    "retorno; máx. 1 por dia por cliente). Acordos vêm do SIAC. "
    f"O que é registrado no SIAC aparece em até {config.TTL_CONTATOS // 60} min."
)

# ---------------------------- rotina do dia --------------------------------
st.divider()
st.subheader("🗓️ Rotina do dia")
st.caption(
    "Monta a lista de quem ligar hoje: **primeiro os seus acordos com parcela vencida** "
    "(mesmo fora da carteira), depois os clientes da carteira — quem ainda não teve contato, "
    "depois quem está há mais tempo sem contato (loja mais crítica e maior débito desempatam). "
    "Quem já teve contato hoje e quem já pagou tudo ficam de fora."
)
r1, r2 = st.columns([1, 3])
tamanho = r1.number_input(
    "Quantos clientes da carteira", min_value=1, max_value=60, value=config.ROTINA_TAMANHO_PADRAO
)
r2.write("")
r2.write("")
gerar = r2.button("⚡ Gerar rotina", type="primary")

acordos_atr = servico.clientes_acordo_atrasado(ciclo, cod)
lista = servico.rotina(
    ciclo, cod, meus, gerar=gerar, tamanho=int(tamanho), acordos_atrasados=acordos_atr
)
if not lista:
    st.info("Nenhuma rotina gerada hoje. Clique em **Gerar rotina**.")
else:
    feitos = servico.contatados_hoje(ciclo)
    por_cod = {}
    if not acordos_atr.is_empty():
        por_cod = {r["codcli"]: r for r in acordos_atr.iter_rows(named=True)}
        feitos |= set(acordos_atr.filter(pl.col("contatado_hoje"))["codcli"].to_list())
    # quem está na carteira usa a linha completa da carteira (com acordo e status)
    por_cod.update({r["codcli"]: r for r in meus.iter_rows(named=True)})
    codigos_atr = set(acordos_atr["codcli"].to_list()) if not acordos_atr.is_empty() else set()
    lista = [c for c in lista if c in por_cod]
    st.progress(
        sum(c in feitos for c in lista) / len(lista),
        text=f"Rotina de hoje: {sum(c in feitos for c in lista)} de {len(lista)} com contato hoje",
    )
    autor = sessao.cod_usuario()
    for i, codcli in enumerate(lista, start=1):
        cli = por_cod[codcli]
        marca = "✅" if codcli in feitos else "⬜"
        if codcli in codigos_atr:
            linha_acordo = next(
                r for r in acordos_atr.iter_rows(named=True) if r["codcli"] == codcli
            )
            titulo = (
                f"{marca} {i}. ⚠️ ACORDO ATRASADO · {codcli} · {cli.get('cliente') or ''} — "
                f"{cli.get('loja') or ''} · {linha_acordo['atrasadas']} parcela(s) · "
                f"{ui.brl(linha_acordo['vl_atrasado'])} em atraso"
            )
        else:
            titulo = (
                f"{marca} {i}. {codcli} · {cli.get('cliente') or ''} — {cli['loja']} · "
                f"{ui.brl(cli['vl_faixa'])} na faixa · "
                f"{cli['contatos']}/{config.META_CONTATOS} contatos"
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

# ---------------------------- simulador de acordo --------------------------
st.divider()
st.subheader("🧮 Simulador de acordo")
st.caption(
    "Mesmas contas da tela de Acordos do SIAC. Só simula — o acordo continua sendo lançado no SIAC."
)
# clientes da carteira + clientes dos meus acordos (fora da faixa também)
rot_sim = dict(rotulos)
if not acordos.is_empty():
    for r in acordos.select("codcli", "cliente").iter_rows():
        rot_sim.setdefault(r[0], f"{r[0]} · {r[1] or ''} (acordo)")
cli_sim = st.selectbox(
    "Cliente para simular",
    sorted(rot_sim),
    format_func=rot_sim.get,
    index=None,
    placeholder="Busque pelo código ou nome",
    key="sim_cliente",
)
if cli_sim:
    with st.container(border=True, key="cartao_simulador"):
        calculadora_acordo(cli_sim, chave=f"sim_{cli_sim}")

ui.rodape_atualizacao()
