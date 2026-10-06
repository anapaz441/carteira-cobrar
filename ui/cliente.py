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
        _linha("Contatos no mês", f"{cli['contatos']} de {config.META_CONTATOS}")
        _linha(
            "Último contato",
            f"{cli.get('ult_contato') or '—'} · {cli.get('ult_resultado') or ''}",
        )
        if cli.get("ult_texto"):
            st.caption(f"📝 {cli['ult_texto']}")

    with dir_:
        opcoes = servico.tipos_resultado()
        rotulos = dict(opcoes)
        with st.form(f"form_{chave}", clear_on_submit=True, border=True):
            resultado = st.selectbox(
                "Resultado",
                [c for c, _ in opcoes],
                format_func=rotulos.get,
                index=None,
                placeholder="Escolha o resultado da ligação",
                key=f"res_{chave}",
            )
            texto = st.text_area(
                "Escreva a anotação",
                key=f"txt_{chave}",
                height=110,
                placeholder="Ex.: falei com o João, paga R$ 500 na sexta e o resto dia 20.",
            )
            if st.form_submit_button("💾 Salvar anotação", type="primary"):
                if resultado is None:
                    st.warning("Escolha o resultado (ou 'Só anotação').")
                elif not texto.strip():
                    st.warning("Escreva alguma coisa antes de salvar.")
                else:
                    servico.registrar_anotacao(cli["codcli"], autor, resultado, texto)
                    st.toast(f"Anotação salva para {cli['codcli']}.", icon="✅")
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
