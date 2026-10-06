"""Carteira de Cobrança — ponto de entrada (só configuração e navegação)."""

import streamlit as st

from data import carteira_store

st.set_page_config(page_title="Carteira de Cobrança", page_icon="📞", layout="wide")

# Cria o arquivo da carteira (SQLite) e o cadastro inicial de cobradores, se faltarem
carteira_store.inicializar()

paginas = {
    "Cobrança": [
        st.Page(
            "views/carteira_cobrador.py",
            title="Minha carteira",
            icon="📞",
            default=True,
        ),
        st.Page("views/visao_geral.py", title="Visão geral", icon="📊"),
    ],
    "Gestão": [
        st.Page("views/gerar.py", title="Gerar carteira", icon="⚙️"),
        st.Page("views/cobradores.py", title="Cobradores", icon="👥"),
    ],
}
st.navigation(paginas).run()
