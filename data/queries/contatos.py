"""Consultas das ligações de cobrança registradas no SIAC.

Tabelas:
- `cobranca`  → cada ligação (data, hora, cobrador = cd_usuario, resultado = cd_negocia)
- `cobratxt`  → anotação da ligação (junta por cd_loja + sq_cobran)
- `cobtpneg`  → descrição do resultado ("TELEFONE NAO ATENDE", "EM NEGOCIACAO"...)
"""

from datetime import date

import pandas as pd
import streamlit as st

import config
from data.connection import get_conn


@st.cache_data(ttl=config.TTL_CONTATOS, show_spinner=False)
def contatos_no_ciclo(inicio: date, codigos: tuple[str, ...]) -> pd.DataFrame:
    """Uma linha por ligação feita para os clientes da carteira desde o início do ciclo.

    Vem "linha a linha" (são poucas: ~150 clientes x poucas ligações) para o
    domínio contar contatos por cliente, por dia e por cobrador.
    """
    if not codigos:
        return pd.DataFrame(
            columns=["codcli", "dt_cobran", "hr_cobran", "cd_usuario", "cd_negocia"]
        )
    sql = """
        SELECT c.cd_cliente AS codcli, c.dt_cobran, c.hr_cobran,
               c.cd_usuario, c.cd_negocia
        FROM public.cobranca c
        WHERE c.dt_cobran >= :inicio
          AND c.cd_cliente = ANY(:codigos)
    """
    df = get_conn().query(
        sql,
        params={"inicio": inicio, "codigos": list(codigos)},
        ttl=config.TTL_CONTATOS,
    )
    df["dt_cobran"] = pd.to_datetime(df["dt_cobran"]).dt.date
    return df


@st.cache_data(ttl=config.TTL_CONTATOS, show_spinner=False)
def ultimo_contato(codigos: tuple[str, ...]) -> pd.DataFrame:
    """Última ligação registrada para cada cliente (qualquer cobrador, último ano)."""
    if not codigos:
        return pd.DataFrame()
    sql = """
        WITH ult AS (
            SELECT DISTINCT ON (c.cd_cliente)
                   c.cd_cliente, c.cd_loja, c.sq_cobran, c.dt_cobran, c.hr_cobran,
                   c.cd_usuario, c.cd_negocia, c.dt_proxlig
            FROM public.cobranca c
            WHERE c.dt_cobran >= CURRENT_DATE - :dias
              AND c.cd_cliente = ANY(:codigos)
            ORDER BY c.cd_cliente, c.dt_cobran DESC, c.hr_cobran DESC
        )
        SELECT u.cd_cliente AS codcli, u.dt_cobran AS ult_data, u.hr_cobran AS ult_hora,
               u.cd_usuario AS ult_usuario, n.ds_negocia AS ult_resultado,
               t.tx_cobran AS ult_texto, u.dt_proxlig AS prox_ligacao
        FROM ult u
        LEFT JOIN public.cobtpneg n ON n.cd_negocia = u.cd_negocia
        LEFT JOIN public.cobratxt t ON t.cd_loja = u.cd_loja AND t.sq_cobran = u.sq_cobran
    """
    return get_conn().query(
        sql,
        params={"dias": config.DIAS_HISTORICO_ULTIMO_CONTATO, "codigos": list(codigos)},
        ttl=config.TTL_CONTATOS,
    )


@st.cache_data(ttl=config.TTL_CONTATOS, show_spinner=False)
def historico_cliente(codcli: str, dias: int = 120) -> pd.DataFrame:
    """Todas as ligações de um cliente nos últimos `dias` dias, com a anotação."""
    sql = """
        SELECT c.dt_cobran AS data, c.hr_cobran AS hora, c.cd_usuario,
               d.loja, n.ds_negocia AS resultado, t.tx_cobran AS anotacao,
               c.vl_total AS valor_cobrado, c.dt_proxlig AS prox_ligacao
        FROM public.cobranca c
        LEFT JOIN public.cobtpneg n ON n.cd_negocia = c.cd_negocia
        LEFT JOIN public.dlojas d   ON d.cd_loja = c.cd_loja
        LEFT JOIN public.cobratxt t ON t.cd_loja = c.cd_loja AND t.sq_cobran = c.sq_cobran
        WHERE c.cd_cliente = :codcli
          AND c.dt_cobran >= CURRENT_DATE - :dias
        ORDER BY c.dt_cobran DESC, c.hr_cobran DESC
    """
    return get_conn().query(sql, params={"codcli": codcli, "dias": dias}, ttl=config.TTL_CONTATOS)


@st.cache_data(ttl=config.TTL_FREQUENTE, show_spinner=False)
def usuarios_que_cobraram(dias: int = 30) -> pd.DataFrame:
    """Códigos de usuário que registraram ligações de cobrança nos últimos `dias` dias.
    Ajuda a descobrir o código de cada cobrador no SIAC."""
    sql = """
        SELECT c.cd_usuario, COUNT(*) AS ligacoes, COUNT(DISTINCT c.cd_cliente) AS clientes,
               MAX(c.dt_cobran) AS ultima_ligacao
        FROM public.cobranca c
        WHERE c.dt_cobran >= CURRENT_DATE - :dias
        GROUP BY c.cd_usuario
        ORDER BY ligacoes DESC
    """
    return get_conn().query(sql, params={"dias": dias}, ttl=config.TTL_FREQUENTE)
