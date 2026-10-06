"""Tela: Cadastro de cobradores (nome, código do SIAC, integral/parcial)."""

import streamlit as st

import config
from data import carteira_store as store
from data.queries import contatos as q_contatos
from domain.distribuicao import fatias
from domain.servico import cobradores

st.title("👥 Cobradores")
st.write(
    "O **código** é o usuário do SIAC que aparece nas ligações de cobrança. "
    f"Tempo integral tem peso 1; parcial tem peso {config.PESO_TIPO['Parcial']:.2f} "
    "(fica com 1/4 a menos de clientes e de valor). Desmarque **Ativo** para tirar alguém "
    "da próxima carteira."
)

editado = st.data_editor(
    store.listar_cobradores(),
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    column_config={
        "cod_usuario": st.column_config.TextColumn("Código SIAC", required=True),
        "nome": st.column_config.TextColumn("Nome", required=True),
        "tipo": st.column_config.SelectboxColumn(
            "Tipo", options=list(config.PESO_TIPO), required=True, default="Integral"
        ),
        "ativo": st.column_config.CheckboxColumn("Ativo", default=True),
    },
    key="editor_cobradores",
)
if st.button("💾 Salvar cobradores", type="primary"):
    if editado["cod_usuario"].astype(str).str.strip().duplicated().any():
        st.error("Há códigos repetidos.")
    else:
        store.salvar_cobradores(editado)
        st.success("Cadastro salvo.")
        st.rerun()

ativos = cobradores()
if not ativos.is_empty():
    st.caption(
        "Fatia de cada um na próxima carteira: "
        + " · ".join(
            f"{n}: {f * 100:.1f}%".replace(".", ",")
            for n, f in zip(ativos["nome"].to_list(), fatias(ativos).values(), strict=True)
        )
    )

with st.expander("Não sabe o código? Veja quem registrou ligações nos últimos 30 dias"):
    st.dataframe(
        q_contatos.usuarios_que_cobraram(),
        hide_index=True,
        width="stretch",
        column_config={
            "cd_usuario": "Código SIAC",
            "ligacoes": "Ligações",
            "clientes": "Clientes",
            "ultima_ligacao": st.column_config.DateColumn("Última", format="DD/MM/YYYY"),
        },
    )
