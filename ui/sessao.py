"""Quem está usando o app (perfil guardado na sessão de cada pessoa)."""

import streamlit as st

PERFIL_COBRADOR = "cobrador"
PERFIL_GESTOR = "gestor"
USUARIO_GESTOR = "GESTOR"  # código gravado nas anotações feitas pelo gestor


def perfil() -> str | None:
    return st.session_state.get("perfil")


def cod_usuario() -> str:
    """Código de quem está logado (matrícula do cobrador ou 'GESTOR')."""
    return st.session_state.get("cod_usuario", USUARIO_GESTOR)


def entrar(perfil_: str, cod: str, nome: str) -> None:
    st.session_state["perfil"] = perfil_
    st.session_state["cod_usuario"] = cod
    st.session_state["nome_usuario"] = nome


def sair() -> None:
    for k in ("perfil", "cod_usuario", "nome_usuario"):
        st.session_state.pop(k, None)


def exigir_gestor() -> None:
    """Para a tela se quem está logado não for gestor."""
    if perfil() != PERFIL_GESTOR:
        st.error("Esta tela é só para a gestão.")
        st.stop()
