"""Consultas de títulos em aberto (contas a receber — tabela `lanca` do SIAC).

Regras (validadas pelo MCP):
- título em aberto = tipo 'R' (receber) e `pagamento` vazio
- contas de débito = config.CONTAS_DEBITO (venda faturada + Serasa automático)
- só lojas da carteira (config.LOJAS_CARTEIRA)
"""

import pandas as pd
import streamlit as st

import config
from data.connection import get_conn

# Bloco comum: títulos vencidos e em aberto das lojas/contas da carteira.
_SQL_ABERTOS = """
    SELECT l.codclifor, l.cd_loja, l.vencimento, l.valor
    FROM public.lanca l
    WHERE l.pagamento IS NULL
      AND l.tipo = 'R'
      AND l.codcon = ANY(:contas)
      AND l.cd_loja = ANY(:lojas)
      AND l.vencimento < CURRENT_DATE
"""

# Agregação por cliente: débito total, débito na faixa, loja principal e contato.
_SQL_AGREGA = """
, por_loja AS (
    SELECT a.codclifor, a.cd_loja,
           ROW_NUMBER() OVER (PARTITION BY a.codclifor ORDER BY SUM(a.valor) DESC) AS rk
    FROM abertos a JOIN alvo USING (codclifor)
    GROUP BY a.codclifor, a.cd_loja
), agg AS (
    SELECT a.codclifor,
           COUNT(*)                                   AS qt_titulos,
           SUM(a.valor)                               AS vl_vencido,
           COUNT(*) FILTER (WHERE a.vencimento BETWEEN CURRENT_DATE - :dmax AND CURRENT_DATE - :dmin)
                                                      AS qt_faixa,
           COALESCE(SUM(a.valor) FILTER (WHERE a.vencimento BETWEEN CURRENT_DATE - :dmax
                                                              AND CURRENT_DATE - :dmin), 0)
                                                      AS vl_faixa,
           CURRENT_DATE - MIN(a.vencimento)           AS dias_atraso_max,
           STRING_AGG(DISTINCT a.cd_loja, ',')        AS lojas
    FROM abertos a JOIN alvo USING (codclifor)
    GROUP BY a.codclifor
)
SELECT g.codclifor AS codcli, p.cd_loja AS loja_principal, g.lojas,
       g.qt_titulos, g.vl_vencido, g.qt_faixa, g.vl_faixa, g.dias_atraso_max,
       c.cliente, c.fantasia,
       NULLIF(TRIM(COALESCE(c.ddd, '') || ' ' || COALESCE(c.telefone, '')), '')   AS telefone,
       NULLIF(TRIM(COALESCE(c.nu_dddsms, '') || ' ' || COALESCE(c.nu_telsms, '')), '') AS whatsapp,
       c.email_fin AS email
FROM agg g
JOIN por_loja p ON p.codclifor = g.codclifor AND p.rk = 1
LEFT JOIN public.cliente c ON c.codcli = g.codclifor
"""


def _params() -> dict:
    return {
        "contas": list(config.CONTAS_DEBITO),
        "lojas": list(config.LOJAS_CARTEIRA),
        "dmin": config.DIAS_ATRASO_MIN,
        "dmax": config.DIAS_ATRASO_MAX,
    }


def _tipar(df: pd.DataFrame) -> pd.DataFrame:
    """Garante tipos numéricos (o Postgres devolve numeric como Decimal)."""
    for col in ("vl_vencido", "vl_faixa"):
        df[col] = pd.to_numeric(df[col]).astype(float)
    for col in ("qt_titulos", "qt_faixa", "dias_atraso_max"):
        df[col] = pd.to_numeric(df[col]).astype(int)
    return df


@st.cache_data(ttl=config.TTL_FREQUENTE, show_spinner=False)
def clientes_elegiveis() -> pd.DataFrame:
    """Clientes com pelo menos 1 título vencido entre 16 e 60 dias (hoje)."""
    sql = (
        f"WITH abertos AS ({_SQL_ABERTOS}), "
        "alvo AS (SELECT DISTINCT codclifor FROM abertos "
        "         WHERE vencimento BETWEEN CURRENT_DATE - :dmax AND CURRENT_DATE - :dmin)"
        + _SQL_AGREGA
    )
    df = get_conn().query(sql, params=_params(), ttl=config.TTL_FREQUENTE)
    return _tipar(df)


@st.cache_data(ttl=config.TTL_FREQUENTE, show_spinner=False)
def situacao_atual(codigos: tuple[str, ...]) -> pd.DataFrame:
    """Débito ATUAL dos clientes que estão na carteira (mesmo que já tenham pago
    ou saído da faixa). Cliente que não aparece no resultado = sem débito vencido."""
    if not codigos:
        return pd.DataFrame()
    sql = (
        f"WITH abertos AS ({_SQL_ABERTOS} AND l.codclifor = ANY(:codigos)), "
        "alvo AS (SELECT DISTINCT codclifor FROM abertos)" + _SQL_AGREGA
    )
    df = get_conn().query(
        sql, params={**_params(), "codigos": list(codigos)}, ttl=config.TTL_FREQUENTE
    )
    return _tipar(df)
