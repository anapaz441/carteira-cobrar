"""Consultas de acordos (tabelas `acordo` e `acor_par` do SIAC).

Situação do acordo (acordo.in_situaca), conferida no banco em 06/10/2026:
- 'A' = ativo · 'N' = ativo recém-cadastrado
- 'I' = inativo / quebrado (todos têm parcela vencida sem pagamento)
- 'Q' = quitado (todas as parcelas pagas)
"""

import pandas as pd
import streamlit as st

import config
from data.connection import get_conn


@st.cache_data(ttl=config.TTL_FREQUENTE, show_spinner=False)
def acordos_clientes(codigos: tuple[str, ...]) -> pd.DataFrame:
    """Acordo mais relevante de cada cliente: o ativo, se existir; senão o mais recente.
    Inclui o andamento das parcelas (pagas, atrasadas, próximo vencimento)."""
    colunas = [
        "codcli",
        "situacao_acordo",
        "dt_acordo",
        "vl_acordo",
        "vl_parcela",
        "parcelas",
        "pagas",
        "atrasadas",
        "prox_vcto",
    ]
    if not codigos:
        return pd.DataFrame(columns=colunas)
    sql = """
        WITH ac AS (
            SELECT a.cd_cliente AS codcli, a.cd_loja, a.sq_acordo, a.in_situaca,
                   a.dt_acordo, a.vl_atualiz, a.vl_parcela,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.cd_cliente
                       ORDER BY (a.in_situaca IN ('A', 'N')) DESC, a.dt_acordo DESC, a.hbrecno DESC
                   ) AS rk
            FROM public.acordo a
            WHERE a.cd_cliente = ANY(:codigos)
        ), par AS (
            SELECT p.cd_loja, p.sq_acordo,
                   COUNT(*)                                                     AS parcelas,
                   COUNT(*) FILTER (WHERE p.dt_pgto IS NOT NULL)                AS pagas,
                   COUNT(*) FILTER (WHERE p.dt_pgto IS NULL
                                      AND p.dt_vcto < CURRENT_DATE)             AS atrasadas,
                   MIN(p.dt_vcto) FILTER (WHERE p.dt_pgto IS NULL)              AS prox_vcto
            FROM public.acor_par p
            JOIN ac ON ac.cd_loja = p.cd_loja AND ac.sq_acordo = p.sq_acordo AND ac.rk = 1
            GROUP BY p.cd_loja, p.sq_acordo
        )
        SELECT ac.codcli, ac.in_situaca AS situacao_acordo, ac.dt_acordo,
               ac.vl_atualiz AS vl_acordo, ac.vl_parcela,
               COALESCE(par.parcelas, 0) AS parcelas, COALESCE(par.pagas, 0) AS pagas,
               COALESCE(par.atrasadas, 0) AS atrasadas, par.prox_vcto
        FROM ac
        LEFT JOIN par ON par.cd_loja = ac.cd_loja AND par.sq_acordo = ac.sq_acordo
        WHERE ac.rk = 1
    """
    df = get_conn().query(sql, params={"codigos": list(codigos)}, ttl=config.TTL_FREQUENTE)
    for col in ("vl_acordo", "vl_parcela"):
        df[col] = pd.to_numeric(df[col]).astype(float)
    for col in ("parcelas", "pagas", "atrasadas"):
        df[col] = pd.to_numeric(df[col]).astype(int)
    return df


@st.cache_data(ttl=config.TTL_FREQUENTE, show_spinner=False)
def acordos_ativos() -> pd.DataFrame:
    """Todos os acordos ATIVOS (A/N) dos últimos 2 anos, com o andamento das parcelas e as
    observações (é nelas que o cobrador assina quem fechou o acordo)."""
    sql = """
        SELECT a.cd_loja, a.sq_acordo, a.cd_cliente AS codcli, c.cliente,
               a.in_situaca AS situacao_acordo, a.dt_acordo, a.vl_atualiz AS vl_acordo,
               a.vl_parcela, COALESCE(a.tx_obs1, '') AS obs1, COALESCE(a.tx_obs2, '') AS obs2,
               COUNT(p.hbrecno)                                                  AS parcelas,
               COUNT(p.hbrecno) FILTER (WHERE p.dt_pgto IS NOT NULL)            AS pagas,
               COUNT(p.hbrecno) FILTER (WHERE p.dt_pgto IS NULL
                                          AND p.dt_vcto < CURRENT_DATE)         AS atrasadas,
               COALESCE(SUM(p.vl_parcela) FILTER (WHERE p.dt_pgto IS NULL
                                                    AND p.dt_vcto < CURRENT_DATE), 0) AS vl_atrasado,
               MIN(p.dt_vcto) FILTER (WHERE p.dt_pgto IS NULL)                  AS prox_vcto
        FROM public.acordo a
        LEFT JOIN public.acor_par p ON p.cd_loja = a.cd_loja AND p.sq_acordo = a.sq_acordo
        LEFT JOIN public.cliente c  ON c.codcli = a.cd_cliente
        WHERE a.in_situaca = ANY(:ativos)
          AND a.dt_acordo >= CURRENT_DATE - 730
        GROUP BY a.cd_loja, a.sq_acordo, a.cd_cliente, c.cliente, a.in_situaca, a.dt_acordo,
                 a.vl_atualiz, a.vl_parcela, a.tx_obs1, a.tx_obs2
    """
    df = get_conn().query(
        sql, params={"ativos": list(config.ACORDO_ATIVO)}, ttl=config.TTL_FREQUENTE
    )
    for col in ("vl_acordo", "vl_parcela", "vl_atrasado"):
        df[col] = pd.to_numeric(df[col]).astype(float)
    for col in ("parcelas", "pagas", "atrasadas"):
        df[col] = pd.to_numeric(df[col]).astype(int)
    return df


@st.cache_data(ttl=config.TTL_CONTATOS, show_spinner=False)
def titulos_para_acordo(codcli: str) -> pd.DataFrame:
    """Títulos que o SIAC ofereceria num acordo novo para o cliente (mesma regra da tela
    de Acordos, ACO000.prg → fCarregaDuplicatas_Aco):
    - títulos a receber em aberto (sem pagamento), vencidos até ontem (dDt_FimAux = hoje-1);
    - fora os que já estão num acordo ATIVO, QUITADO ou NÃO AUTORIZADO.
    Vem de todas as lojas com `cd_loja`: o acordo no SIAC é por loja (cada loja tem o seu
    LANCA), então a tela separa por loja — 27 clientes têm acordos em mais de uma loja."""
    sql = """
        SELECT l.cd_loja, l.codlan, l.duplicata, l.codcon, l.vencimento, l.valor,
               COALESCE(l.juros, 0) AS juros, COALESCE(l.multa, 0) AS multa
        FROM public.lanca l
        WHERE l.codclifor = :codcli
          AND l.tipo = 'R'
          AND l.pagamento IS NULL
          AND l.vencimento < CURRENT_DATE
          AND NOT EXISTS (
              SELECT 1
              FROM public.acor_lan al
              JOIN public.acordo a ON a.cd_loja = al.cd_loja AND a.sq_acordo = al.sq_acordo
              WHERE al.sq_lancame = l.codlan
                AND al.cd_loja = l.cd_loja
                AND a.in_situaca IN ('A', 'Q', 'N')
          )
        ORDER BY l.vencimento
    """
    df = get_conn().query(sql, params={"codcli": codcli}, ttl=config.TTL_CONTATOS)
    for col in ("valor", "juros", "multa"):
        df[col] = pd.to_numeric(df[col]).astype(float)
    return df
