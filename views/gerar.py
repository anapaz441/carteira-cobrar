"""Tela: Gerar carteira (gestão) — monta a carteira do mês, encaixa novos e ajusta."""

import polars as pl
import streamlit as st

import config
from data import carteira_store as store
from domain import servico
from ui import componentes as ui
from ui import sessao

st.title("⚙️ Gerar carteira")
sessao.exigir_gestor()

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
st.text_input("Mês", f"{mes[5:]}/{mes[:4]}", disabled=True)
st.caption("Os contatos do mês contam a partir do dia 1.")

if st.button("🔎 Ver prévia da distribuição", type="secondary"):
    with st.spinner("Buscando clientes em atraso no SIAC..."):
        st.session_state["previa"] = servico.previa_distribuicao()

if "previa" in st.session_state:
    dist, conf = st.session_state["previa"]
    st.success(
        f"**{dist.height} clientes** · títulos de 16–60 dias: "
        f"**{ui.brl(dist['vl_faixa'].sum())}** · tudo que esses clientes devem vencido "
        f"(inclui títulos com mais de 60 e menos de 16 dias): "
        f"**{ui.brl(dist['vl_vencido'].sum())}**"
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
            servico.gerar_carteira(mes, dist=dist)
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

    # ---------------- 3. redistribuir pelo relacionamento --------------------
    st.subheader("3. Refazer a carteira deste mês pelo relacionamento")
    st.markdown(
        "Usa **só os clientes que hoje estão na faixa 16–60 dias** e mantém cada um com "
        "**quem já fala com ele**: primeiro quem **fechou o acordo ativo**; depois quem "
        "**mais ligou nos últimos 60 dias** — os clientes das **lojas críticas** escolhem "
        "primeiro. Cada cobrador tem um **teto** "
        "(a fatia justa: integral ~19%, parcial ~14%); se o preferido estiver cheio, vai para o "
        "próximo que já falou com o cliente, e quem sobrar é dividido de forma equilibrada.  \n"
        "Só troca o cobrador — anotações, contatos e o recuperado de cada cliente continuam."
    )
    if st.button("🔎 Ver prévia pelo relacionamento"):
        with st.spinner("Lendo o histórico de ligações e os acordos no SIAC..."):
            st.session_state["previa_rel"] = servico.previa_relacionamento(ciclo)

    if "previa_rel" in st.session_state:
        prev, saem = st.session_state["previa_rel"]
        nomes_rel = dict(servico.cobradores(False).select("cod_usuario", "nome").iter_rows())
        resumo_rel = (
            prev.group_by("cod_usuario")
            .agg(
                pl.len().alias("clientes"),
                pl.col("vl_faixa").sum().alias("vl_faixa"),
                (pl.col("motivo") == "Fechou o acordo").sum().alias("acordo"),
                pl.col("motivo").str.contains("falou").sum().alias("relacionamento"),
                pl.col("motivo").str.starts_with("Equilíbrio").sum().alias("equilibrio"),
                (pl.col("cod_usuario") == pl.col("cod_antigo")).sum().alias("ja_era_dele"),
            )
            .join(
                prev.filter(pl.col("cod_antigo").is_not_null())
                .group_by("cod_antigo")
                .len()
                .rename({"cod_antigo": "cod_usuario", "len": "antes"}),
                on="cod_usuario",
                how="full",
                coalesce=True,
            )
            .with_columns(
                pl.col("cod_usuario")
                .replace_strict(nomes_rel, default=None, return_dtype=pl.Utf8)
                .fill_null(pl.col("cod_usuario"))
                .alias("nome"),
                pl.all().exclude("cod_usuario", "nome", "vl_faixa").fill_null(0),
            )
            .sort("nome")
        )
        mudam = prev.filter(pl.col("cod_usuario") != pl.col("cod_antigo")).height
        entram = prev.filter(pl.col("cod_antigo").is_null()).height
        st.info(
            f"Carteira nova: **{prev.height} clientes** (só quem está hoje na faixa 16–60d). "
            f"**{mudam}** mudam de cobrador · **{entram}** entram (chegaram na faixa depois) · "
            f"**{saem.height}** saem (não estão mais na faixa)."
        )
        st.dataframe(
            resumo_rel.select(
                "nome",
                "antes",
                "clientes",
                "vl_faixa",
                "acordo",
                "relacionamento",
                "equilibrio",
                "ja_era_dele",
            ).to_pandas(),
            hide_index=True,
            width="stretch",
            column_config={
                "nome": "Cobrador",
                "antes": "Clientes hoje",
                "clientes": "Clientes depois",
                "vl_faixa": st.column_config.NumberColumn("Débito 16–60d (R$)", format="localized"),
                "acordo": "Por acordo",
                "relacionamento": "Por ligações",
                "equilibrio": "Por equilíbrio",
                "ja_era_dele": "Já eram dele(a)",
            },
        )
        with st.expander("Ver cliente a cliente"):
            st.dataframe(
                prev.with_columns(
                    pl.col("cod_antigo")
                    .replace_strict(nomes_rel, default=None, return_dtype=pl.Utf8)
                    .alias("antes"),
                    pl.col("cod_usuario")
                    .replace_strict(nomes_rel, default=None, return_dtype=pl.Utf8)
                    .alias("depois"),
                )
                .select(
                    "codcli", "cliente", "loja_principal", "vl_faixa", "antes", "depois", "motivo"
                )
                .to_pandas(),
                hide_index=True,
                width="stretch",
                column_config={
                    "codcli": "Código",
                    "cliente": "Cliente",
                    "loja_principal": "Loja",
                    "vl_faixa": st.column_config.NumberColumn(
                        "Débito 16–60d (R$)", format="localized"
                    ),
                    "antes": "Cobrador hoje",
                    "depois": "Novo cobrador",
                    "motivo": "Motivo",
                },
            )
        ok = st.checkbox(
            f"Sim, quero aplicar na carteira de {mes[5:]}/{mes[:4]} "
            "(as próximas carteiras continuam pela regra de equilíbrio)"
        )
        if st.button("✅ Aplicar relacionamento", type="primary", disabled=not ok):
            trocados = servico.aplicar_relacionamento(ciclo["id"], prev, saem)
            st.session_state.pop("previa_rel", None)
            st.success(f"Pronto! {trocados} cliente(s) mudaram de cobrador.")
            st.rerun()

    # ------------------------ 4. ajuste manual -------------------------------
    st.subheader("4. Trocar cliente de cobrador")
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
