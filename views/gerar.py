"""Tela: Gerar carteira (gestão) — monta a carteira do mês, encaixa novos e ajusta."""

from datetime import date

import polars as pl
import streamlit as st

import config
from data import carteira_store as store
from domain import servico
from ui import componentes as ui

st.title("⚙️ Gerar carteira")

cob = servico.cobradores()
if cob.is_empty():
    st.error("Nenhum cobrador ativo. Cadastre em **Cobradores** antes de gerar a carteira.")
    st.stop()

if cob["nome"].str.starts_with("Cobrador ").any():
    st.warning(
        'Alguns cobradores ainda estão com nome provisório ("Cobrador 1234"). '
        "Confira nomes, códigos e quem é parcial na tela **Cobradores**."
    )

st.markdown(
    f"""
**Regra da carteira**
- Entra todo cliente com **pelo menos 1 título vencido entre {config.DIAS_ATRASO_MIN} e
  {config.DIAS_ATRASO_MAX} dias** (venda faturada + Serasa automático), nas lojas:
  {", ".join(config.LOJAS_PRIORIDADE.values())} (nessa ordem de prioridade).
- Tempo integral = peso 1 · Parcial = peso {config.PESO_TIPO["Parcial"]:.2f}
  (1/4 a menos). A quantidade de clientes e o **débito 16–60 dias** ficam proporcionais
  a esse peso, e cada loja é espalhada entre todos.
"""
)

# ---------------------------- 1. prévia / gerar -----------------------------
st.subheader("1. Carteira do mês")
mes = servico.mes_atual()
ciclo = store.obter_ciclo(mes)
col1, col2 = st.columns(2)
col1.text_input("Mês", f"{mes[5:]}/{mes[:4]}", disabled=True)
inicio = col2.date_input(
    "Contar contatos a partir de",
    value=date.today(),
    format="DD/MM/YYYY",
    help="Ligações registradas no SIAC a partir desta data contam para a meta.",
)

if st.button("🔎 Ver prévia da distribuição", type="secondary"):
    with st.spinner("Buscando clientes em atraso no SIAC..."):
        st.session_state["previa"] = servico.previa_distribuicao()

if "previa" in st.session_state:
    dist, conf = st.session_state["previa"]
    st.success(
        f"{dist.height} clientes · débito 16–60d {ui.brl(dist['vl_faixa'].sum())} · "
        f"débito vencido total {ui.brl(dist['vl_vencido'].sum())}"
    )
    st.dataframe(
        conf.select(
            "nome",
            "tipo",
            "fatia",
            "clientes",
            "pct_clientes",
            "valor",
            "pct_valor",
            "vl_vencido",
        ).to_pandas(),
        hide_index=True,
        width="stretch",
        column_config={
            "nome": "Cobrador",
            "tipo": "Tipo",
            "fatia": st.column_config.NumberColumn("Fatia justa", format="percent"),
            "clientes": "Clientes",
            "pct_clientes": st.column_config.NumberColumn("% clientes", format="percent"),
            "valor": st.column_config.NumberColumn("Débito 16–60d (R$)", format="localized"),
            "pct_valor": st.column_config.NumberColumn("% débito 16–60d", format="percent"),
            "vl_vencido": st.column_config.NumberColumn("Débito total (R$)", format="localized"),
        },
    )
    st.caption(
        "O débito *total* pode ficar menos equilibrado: poucos clientes têm dívidas muito "
        "antigas e grandes, e um cliente não pode ser dividido entre dois cobradores."
    )

    refazer_ok = True
    if ciclo:
        st.warning(
            f"Já existe carteira para {mes[5:]}/{mes[:4]} (gerada em "
            f"{ui.data_br(ciclo['gerado_em'])}). Salvar vai **refazer** a distribuição."
        )
        refazer_ok = st.checkbox("Sim, quero refazer a carteira do mês")
    if st.button("💾 Salvar carteira do mês", type="primary", disabled=not refazer_ok):
        with st.spinner("Gerando e salvando..."):
            servico.gerar_carteira(mes, inicio, dist)
        st.session_state.pop("previa", None)
        st.success("Carteira salva! Os cobradores já podem ver em **Minha carteira**.")
        st.rerun()

# ---------------------------- 2. novos --------------------------------------
if ciclo:
    st.subheader("2. Clientes que entraram na faixa depois")
    with st.spinner("Conferindo novos clientes..."):
        novos = servico.clientes_novos(ciclo["id"])
    if novos.is_empty():
        st.info("Nenhum cliente novo fora da carteira. 👍")
    else:
        st.write(
            f"**{novos.height}** cliente(s) novos · {ui.brl(novos['vl_faixa'].sum())} na faixa."
        )
        st.dataframe(
            novos.select(
                "codcli",
                "cliente",
                "loja_principal",
                "qt_titulos",
                "vl_faixa",
                "vl_vencido",
            ).to_pandas(),
            hide_index=True,
            width="stretch",
            column_config={
                "codcli": "Código",
                "cliente": "Cliente",
                "loja_principal": "Loja",
                "qt_titulos": "Títulos",
                "vl_faixa": st.column_config.NumberColumn("Débito 16–60d (R$)", format="localized"),
                "vl_vencido": st.column_config.NumberColumn(
                    "Débito total (R$)", format="localized"
                ),
            },
        )
        if st.button("➕ Distribuir novos clientes", type="primary"):
            qtd = servico.distribuir_novos(ciclo["id"])
            st.success(f"{qtd} cliente(s) distribuído(s) sem mexer na carteira atual.")
            st.rerun()

    # ------------------------ 3. ajuste manual -------------------------------
    st.subheader("3. Trocar cliente de cobrador")
    cart = servico.carteira_salva(ciclo["id"])
    nomes = dict(servico.cobradores(False).select("cod_usuario", "nome").iter_rows())
    rot = dict(
        cart.select(
            "codcli",
            pl.concat_str(
                pl.col("codcli"),
                pl.lit(" · "),
                pl.col("fantasia_ini").fill_null(pl.col("cliente_ini")).fill_null(""),
                pl.lit(" ("),
                pl.col("cod_usuario").replace_strict(nomes, default="?", return_dtype=pl.Utf8),
                pl.lit(")"),
            ).alias("rotulo"),
        ).iter_rows()
    )
    a, b, c = st.columns([3, 2, 1])
    cli = a.selectbox(
        "Cliente",
        list(rot),
        format_func=rot.get,
        index=None,
        placeholder="Busque pelo código ou nome",
    )
    novo = b.selectbox("Novo cobrador", cob["cod_usuario"].to_list(), format_func=nomes.get)
    c.write("")
    c.write("")
    if c.button("Trocar", disabled=cli is None):
        store.mover_cliente(ciclo["id"], cli, novo)
        st.success("Cliente movido.")
        st.rerun()
