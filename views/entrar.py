"""Tela: Entrar — escolhe o perfil (cobrador ou gestor)."""

import hmac

import streamlit as st

import config
from domain import servico
from ui import sessao

st.title("📞 Carteira de Cobrança")

tipo = st.radio("Como você vai usar?", ["Sou cobrador(a)", "Sou gestor(a)"], horizontal=True)

if tipo.startswith("Sou cobrador"):
    cob = servico.cobradores(somente_ativos=True)
    nomes = dict(cob.select("cod_usuario", "nome").iter_rows())
    cod = st.selectbox(
        "Seu nome", list(nomes), format_func=nomes.get, index=None, placeholder="Escolha seu nome"
    )
    if st.button("Entrar", type="primary", disabled=cod is None):
        sessao.entrar(sessao.PERFIL_COBRADOR, cod, nomes[cod])
        st.rerun()
else:
    if not config.GESTOR_SENHA:
        st.error(
            "A senha do gestor ainda não foi configurada. Coloque a linha "
            "`GESTOR_SENHA=sua-senha` no arquivo `.env` e reinicie o app."
        )
        st.stop()
    senha = st.text_input("Senha do gestor", type="password")
    if st.button("Entrar", type="primary"):
        if hmac.compare_digest(senha.encode(), config.GESTOR_SENHA.encode()):
            sessao.entrar(sessao.PERFIL_GESTOR, sessao.USUARIO_GESTOR, "Gestão")
            st.rerun()
        else:
            st.error("Senha incorreta.")
