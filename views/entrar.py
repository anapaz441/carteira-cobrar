"""Tela: Entrar — a pessoa escolhe o próprio nome numa lista.

Gestoras (config.GESTORES) digitam a senha GESTOR_SENHA e entram na visão de gestão;
cobradores ativos entram só com o nome, na carteira deles."""

import hmac

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
senha = ""
if cod in gestoras:
    if not config.GESTOR_SENHA:
        caixa.error(
            "A senha da gestão ainda não foi configurada. Coloque a linha "
            "`GESTOR_SENHA=sua-senha` no `.env` (ou nos secrets do servidor) e reinicie o app."
        )
        st.stop()
    senha = caixa.text_input("Senha", type="password", key="senha_gestora")

if caixa.button("Entrar", type="primary", disabled=cod is None, width="stretch"):
    if cod in gestoras:
        if hmac.compare_digest(senha.encode(), config.GESTOR_SENHA.encode()):
            sessao.entrar(sessao.PERFIL_GESTOR, cod, gestoras[cod])
            st.rerun()
        else:
            caixa.error("Senha incorreta.")
    else:
        sessao.entrar(sessao.PERFIL_COBRADOR, cod, cobradores[cod])
        st.rerun()
