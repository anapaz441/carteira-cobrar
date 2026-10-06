"""Tela: Entrar — a pessoa escolhe o próprio nome numa lista (sem senha).

Gestoras (config.GESTORES) entram na visão de gestão; cobradores ativos entram só na
carteira deles. O perfil sai automaticamente do nome escolhido."""

import streamlit as st

import config
from domain import servico
from ui import sessao

_, meio, _ = st.columns([1, 1.4, 1])
caixa = meio.container(border=True, key="cartao_login")
with caixa:
    st.title("📞 Carteira de Cobrança")
    st.caption("Cobrança 16–60 dias · Kaizen")

cob = servico.cobradores(somente_ativos=True)
cobradores = {c: n for c, n in cob.select("cod_usuario", "nome").iter_rows()}
gestoras = {c: n for c, n in config.GESTORES.items() if c not in cobradores}

# gestoras primeiro, depois cobradores (cada grupo em ordem alfabética)
pessoas = {c: f"{n} · Gestão" for c, n in sorted(gestoras.items(), key=lambda x: x[1])}
pessoas |= {c: f"{n} · Cobrador(a)" for c, n in sorted(cobradores.items(), key=lambda x: x[1])}

cod = caixa.selectbox(
    "Quem é você?",
    list(pessoas),
    format_func=pessoas.get,
    index=None,
    placeholder="Escolha seu nome",
    key="pessoa",
)
if caixa.button("Entrar", type="primary", disabled=cod is None, width="stretch"):
    if cod in gestoras:
        sessao.entrar(sessao.PERFIL_GESTOR, cod, gestoras[cod])
    else:
        sessao.entrar(sessao.PERFIL_COBRADOR, cod, cobradores[cod])
    st.rerun()
