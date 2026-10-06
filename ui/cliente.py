"""Cartão do cliente: informações para a ligação + campo para escrever a anotação."""

import streamlit as st

import config
from domain import servico
from ui import componentes as ui


def _linha(rotulo: str, valor: str) -> None:
    st.markdown(f"**{rotulo}:** {valor}")


def cartao_cliente(cli: dict, autor: str, chave: str) -> None:
    """Mostra o cliente e o formulário de anotação.

    cli:   uma linha da carteira (dict) — saída de servico.painel
    autor: código de quem está escrevendo (matrícula do cobrador ou 'GESTOR')
    chave: texto único para os widgets deste cartão
    """
    esq, dir_ = st.columns([3, 2])
    with esq:
        _linha("Cliente", f"{cli['codcli']} · {cli.get('cliente') or ''}")
        if cli.get("fantasia"):
            _linha("Fantasia", cli["fantasia"])
        _linha("Loja", cli.get("loja") or "—")
        _linha("📞 Telefones", cli.get("telefones") or "nenhum cadastrado")
        _linha(
            "Débito",
            f"{ui.brl(cli['vl_faixa'])} na faixa 16–60d · {ui.brl(cli['vl_vencido'])} total · "
            f"{cli['qt_titulos']} título(s) · {cli.get('dias_atraso_max') or 0} dias (máx.)",
        )
        _linha(
            "Contatos no mês",
            f"{cli['contatos']} de {config.META_CONTATOS} (✅ {cli['efetivos']} efetivo(s))",
        )
        _linha(
            "Último contato",
            f"{cli.get('ult_contato') or '—'} · {cli.get('ult_resultado') or ''}",
        )
        if cli.get("ult_texto"):
            st.caption(f"📝 {cli['ult_texto']}")

    with dir_:
        with st.form(f"form_{chave}", clear_on_submit=True, border=True):
            st.markdown("**Registrar contato**")
            tipo = st.radio(
                "O que aconteceu?",
                list(config.TIPOS_CONTATO_APP),
                format_func=config.TIPOS_CONTATO_APP.get,
                index=None,
                key=f"tipo_{chave}",
            )
            canal = st.radio(
                "Por onde?",
                config.CANAIS_CONTATO,
                index=None,
                horizontal=True,
                key=f"canal_{chave}",
            )
            texto = st.text_area(
                "Anotação",
                key=f"txt_{chave}",
                height=90,
                placeholder="Ex.: falei com o João, paga R$ 500 na sexta e o resto dia 20.",
            )
            if st.form_submit_button("💾 Salvar", type="primary", width="stretch"):
                if tipo is None:
                    st.warning("Marque o que aconteceu.")
                elif tipo != config.SO_ANOTACAO and canal is None:
                    st.warning("Marque se foi por ligação ou WhatsApp.")
                elif tipo == config.SO_ANOTACAO and not texto.strip():
                    st.warning("Escreva a anotação.")
                else:
                    servico.registrar_contato(cli["codcli"], autor, tipo, canal, texto)
                    st.toast(f"Registrado para {cli['codcli']}.", icon="✅")
                    st.rerun()

    if st.toggle("Ver histórico de contatos", key=f"hist_{chave}"):
        hist = servico.historico(cli["codcli"])
        if hist.is_empty():
            st.info("Nenhum contato nos últimos 120 dias.")
        else:
            st.dataframe(
                hist.select("quando", "quem", "origem", "resultado", "texto").to_pandas(),
                hide_index=True,
                width="stretch",
                column_config={
                    "quando": "Quando",
                    "quem": "Quem",
                    "origem": "Onde",
                    "resultado": "Resultado",
                    "texto": st.column_config.TextColumn("Anotação", width="large"),
                },
            )
