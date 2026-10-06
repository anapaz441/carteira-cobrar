"""Carteira de Cobrança — ponto de entrada (configuração, perfil e navegação)."""

import streamlit as st

from data import carteira_store
from ui import sessao

st.set_page_config(page_title="Carteira de Cobrança", page_icon="📞", layout="wide")

# Cria o arquivo da carteira (SQLite) e o cadastro inicial de cobradores, se faltarem
carteira_store.inicializar()

perfil = sessao.perfil()
if perfil is None:
    # Ninguém entrou ainda: só a tela de entrada
    paginas = [st.Page("views/entrar.py", title="Entrar", icon="🔑")]
elif perfil == sessao.PERFIL_COBRADOR:
    # Cobrador vê SOMENTE a carteira dele
    paginas = [st.Page("views/carteira_cobrador.py", title="Minha carteira", icon="📞")]
else:
    paginas = {
        "Gestão": [
            st.Page("views/visao_geral.py", title="Visão geral", icon="📊", default=True),
            st.Page("views/carteira_cobrador.py", title="Carteiras dos cobradores", icon="📞"),
            st.Page("views/gerar.py", title="Gerar carteira", icon="⚙️"),
            st.Page("views/cobradores.py", title="Cobradores", icon="👥"),
        ],
    }

if perfil is not None:
    with st.sidebar:
        st.caption(f"Conectado como **{st.session_state.get('nome_usuario', '')}**")
        if st.button("Sair", width="stretch"):
            sessao.sair()
            st.rerun()

st.navigation(paginas).run()
