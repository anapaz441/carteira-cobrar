"""Calculadora de acordo (mesmas contas da tela de Acordos do SIAC) dentro do cartão do cliente."""

from datetime import date

import pandas as pd
import streamlit as st

import config
from data.queries import acordos as q_acordos
from domain import simulador as sim
from ui import componentes as ui


def calculadora_acordo(codcli: str, chave: str) -> None:
    """Simula um acordo para o cliente. Não grava nada: o acordo continua sendo
    lançado no SIAC (tela Acordo de Clientes) — aqui é só para negociar com segurança."""
    df = q_acordos.titulos_para_acordo(codcli)
    if df.empty:
        st.info("Este cliente não tem títulos vencidos disponíveis para um acordo novo.")
        return

    hoje = date.today()

    # No SIAC o acordo é feito DENTRO de uma loja e só junta os títulos daquela loja
    # (cada loja tem o seu LANCA). Cliente devendo em mais de uma loja = um acordo por loja.
    df["cd_loja"] = df["cd_loja"].astype(str)
    lojas = df.groupby("cd_loja", sort=False)["valor"].agg(["count", "sum"])
    if len(lojas) > 1:
        lojas = lojas.sort_values("sum", ascending=False)

        def _rot_loja(cod: str) -> str:
            nome = config.LOJAS_PRIORIDADE.get(cod, "")
            qt, vl = lojas.loc[cod, "count"], lojas.loc[cod, "sum"]
            return f"{cod} {nome} · {qt} título(s) · {ui.brl(vl, markdown=False)}"

        st.info(
            f"Este cliente tem títulos vencidos em **{len(lojas)} lojas**. No SIAC cada acordo "
            "é de uma loja só — simule um de cada vez."
        )
        loja = st.radio(
            "Loja do acordo",
            list(lojas.index),
            format_func=_rot_loja,
            horizontal=True,
            key=f"sim_loja_{chave}",
        )
        df = df[df["cd_loja"] == loja]
        chave = f"{chave}_{loja}"
    else:
        loja = lojas.index[0]
        st.caption(f"Loja do acordo: {loja} {config.LOJAS_PRIORIDADE.get(loja, '')}")

    titulos = [
        sim.Titulo(
            str(r.codlan),
            str(r.duplicata or ""),
            pd.to_datetime(r.vencimento).date(),
            float(r.valor),
            float(r.juros),
            float(r.multa),
        )
        for r in df.itertuples()
    ]

    # ---------------- 1. valores (como o SIAC calcula) ----------------
    c1, c2 = st.columns(2)
    pc_multa = c1.number_input(
        "Multa (%)",
        min_value=0.0,
        max_value=10.0,
        value=config.ACORDO_MULTA,
        step=0.5,
        key=f"sim_multa_{chave}",
    )
    padrao = sim.calcular_titulos(titulos, hoje, None, pc_multa)
    principal, juros, multa, maximo = sim.totais(padrao)
    valor = c2.number_input(
        "Valor do acordo (R$)",
        min_value=float(principal),
        max_value=float(maximo),
        value=float(maximo),
        step=50.0,
        key=f"sim_valor_{chave}_{pc_multa}",
        help="Igual ao SIAC: entre o principal (sem juros) e o valor atualizado (juros 12% "
        "a.m. + multa). Diminuir o valor = dar desconto nos juros.",
    )

    pc_juros, total = sim.juros_para_valor(titulos, hoje, valor, pc_multa)
    if pc_juros is None:
        st.error(
            "Valor impossível com essa multa (nem com 0% de juros chega nesse valor)."
            + (" Sugestão: zerar a multa." if pc_multa > 0 else "")
        )
        return
    desconto = maximo - valor
    _, msg_sit = sim.situacao_prevista(pc_juros, pc_multa)

    def _r(v: float) -> str:
        return ui.brl(v, markdown=False)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Principal", _r(principal), help=f"{len(titulos)} título(s) vencido(s)")
    m2.metric("Atualizado (máx.)", _r(maximo), help="Principal + juros + multa")
    m3.metric("Valor do acordo", _r(valor))
    m4.metric("Juros (a.m.)", f"{pc_juros:.2f}%".replace(".", ","))
    st.caption(
        f"{len(titulos)} título(s) · juros {ui.brl(juros)} · multa {ui.brl(multa)}"
        + (f" · **desconto de {ui.brl(desconto)}**" if desconto > 0.009 else " · sem desconto")
    )
    if pc_juros >= config.ACORDO_JUROS_MIN_AUTOMATICO and pc_multa >= config.ACORDO_MULTA:
        st.success(msg_sit)
    else:
        st.warning(
            f"{msg_sit} (juros abaixo de {config.ACORDO_JUROS_MIN_AUTOMATICO:.2f}% ou multa "
            f"abaixo de {config.ACORDO_MULTA:.0f}%)."
        )

    # ---------------- 2. parcelamento ----------------
    p1, p2, p3 = st.columns(3)
    period = p1.radio(
        "Vencimento",
        ["S", "Q", "M"],
        format_func={"S": "Semanal", "Q": "Quinzenal", "M": "Mensal"}.get,
        horizontal=True,
        key=f"sim_per_{chave}",
    )
    if period == "M":
        dia = str(
            p2.number_input("Dia do mês", 1, 28, value=min(hoje.day, 28), key=f"sim_dia_m_{chave}")
        )
    else:
        dia = p2.selectbox(
            "Dia da semana",
            list(config.ACORDO_DIAS_SEMANA),
            format_func=config.ACORDO_DIAS_SEMANA.get,
            index=4,
            key=f"sim_dia_s_{chave}",
        )
    modo = p3.radio(
        "Parcelar por",
        ["V", "Q"],
        format_func={"V": "Valor da parcela", "Q": "Nº de parcelas"}.get,
        horizontal=True,
        key=f"sim_modo_{chave}",
    )
    q1, q2 = st.columns(2)
    if modo == "V":
        valor_ou_qtd = q1.number_input(
            "Valor da parcela (R$)",
            min_value=config.ACORDO_PARCELA_MIN,
            value=max(config.ACORDO_PARCELA_MIN, round(valor / 10, -1)),
            step=50.0,
            key=f"sim_vparc_{chave}",
        )
    else:
        valor_ou_qtd = q1.number_input("Nº de parcelas", 1, 300, value=10, key=f"sim_qparc_{chave}")
    primeiro = q2.date_input(
        "1º vencimento",
        value=sim.primeiro_vencimento(hoje, period, dia),
        format="DD/MM/YYYY",
        key=f"sim_prim_{chave}_{period}_{dia}",
        help=f"O SIAC aceita até {config.ACORDO_PRIMEIRO_VCTO_MAX_DIAS} dias a partir de hoje.",
    )
    parc = sim.parcelar(total, modo, valor_ou_qtd, period, primeiro, hoje)
    for aviso in parc.avisos:
        st.warning(aviso)
    if parc.quantidade:
        ultima = parc.parcelas[-1]
        st.markdown(
            f"**{parc.quantidade} parcelas**: {parc.quantidade - 1} de "
            f"**{ui.brl(parc.valor_parcela)}** e a última de **{ui.brl(ultima[2])}** · "
            f"de {ui.data_br(parc.parcelas[0][1])} até {ui.data_br(ultima[1])}"
        )

    with st.expander("Ver títulos e parcelas"):
        linhas = sim.calcular_titulos(titulos, hoje, pc_juros, pc_multa)
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Duplicata": x.titulo.duplicata,
                        "Vencimento": x.titulo.vencimento,
                        "Dias": x.dias,
                        "Valor": x.titulo.valor,
                        "Juros": x.juros,
                        "Multa": x.multa,
                        "Total": x.total,
                    }
                    for x in linhas
                ]
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Valor": st.column_config.NumberColumn(format="localized"),
                "Juros": st.column_config.NumberColumn(format="localized"),
                "Multa": st.column_config.NumberColumn(format="localized"),
                "Total": st.column_config.NumberColumn(format="localized"),
            },
        )
        st.dataframe(
            pd.DataFrame(parc.parcelas, columns=["Parcela", "Vencimento", "Valor"]),
            hide_index=True,
            width="stretch",
            column_config={
                "Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Valor": st.column_config.NumberColumn("Valor (R$)", format="localized"),
            },
        )
    st.caption(
        "Simulação com as mesmas regras da tela de Acordos do SIAC (juros por dia de atraso, "
        "multa, parcela mínima e 1º vencimento). Nada é gravado: o acordo é lançado no SIAC."
    )
