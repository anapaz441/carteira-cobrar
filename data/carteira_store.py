"""Camada de dados: onde a carteira gerada fica SALVA.

O SIAC é somente leitura, então a carteira do mês (quem ficou com qual cobrador)
e o cadastro de cobradores ficam num arquivo SQLite do próprio app
(config.CAMINHO_BANCO_CARTEIRA). É estado do app, não ETL: só é escrito quando
alguém clica em "Gerar carteira", "Distribuir novos" ou edita os cobradores.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cobradores (
    cod_usuario TEXT PRIMARY KEY,   -- código do usuário no SIAC (cobranca.cd_usuario)
    nome        TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('Integral', 'Parcial')),
    ativo       INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ciclos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    mes        TEXT NOT NULL UNIQUE,    -- 'AAAA-MM'
    inicio     TEXT NOT NULL,           -- data a partir da qual os contatos contam
    gerado_em  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carteira (
    ciclo_id         INTEGER NOT NULL REFERENCES ciclos(id) ON DELETE CASCADE,
    codcli           TEXT NOT NULL,
    cod_usuario      TEXT NOT NULL,
    loja_principal   TEXT,
    prioridade       INTEGER,
    vl_vencido_ini   REAL,
    vl_faixa_ini     REAL,
    qt_titulos_ini   INTEGER,
    dias_atraso_ini  INTEGER,
    cliente_ini      TEXT,
    fantasia_ini     TEXT,
    telefone_ini     TEXT,
    whatsapp_ini     TEXT,
    origem           TEXT NOT NULL DEFAULT 'geracao',  -- 'geracao' | 'novo' | 'manual'
    entrou_em        TEXT NOT NULL,
    PRIMARY KEY (ciclo_id, codcli)
);
"""

# Cobradores iniciais = os códigos que mais registraram ligações nos últimos 30 dias.
# Nomes e tipo devem ser ajustados na tela "Cobradores".
_COBRADORES_INICIAIS = [
    ("8177", "Cobrador 8177", "Integral"),
    ("4366", "Cobrador 4366", "Integral"),
    ("2281", "Cobrador 2281", "Integral"),
    ("3522", "Cobrador 3522", "Parcial"),
    ("4369", "Cobrador 4369", "Parcial"),
    ("8526", "Cobrador 8526", "Parcial"),
]


@contextmanager
def _conectar():
    caminho = Path(config.CAMINHO_BANCO_CARTEIRA)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")  # leitura e escrita simultâneas sem travar
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def inicializar() -> None:
    """Cria as tabelas (se não existirem) e o cadastro inicial de cobradores."""
    with _conectar() as con:
        con.executescript(_SCHEMA)
        if con.execute("SELECT COUNT(*) FROM cobradores").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO cobradores (cod_usuario, nome, tipo) VALUES (?, ?, ?)",
                _COBRADORES_INICIAIS,
            )


# ----------------------------- cobradores ---------------------------------
def listar_cobradores(somente_ativos: bool = False) -> pd.DataFrame:
    sql = "SELECT cod_usuario, nome, tipo, ativo FROM cobradores"
    if somente_ativos:
        sql += " WHERE ativo = 1"
    with _conectar() as con:
        df = pd.read_sql(sql + " ORDER BY tipo, nome", con)
    df["ativo"] = df["ativo"].astype(bool)
    return df


def salvar_cobradores(df: pd.DataFrame) -> None:
    """Substitui o cadastro de cobradores pelo que foi editado na tela."""
    linhas = [
        (str(r.cod_usuario).strip(), str(r.nome).strip(), r.tipo, int(bool(r.ativo)))
        for r in df.itertuples()
        if str(r.cod_usuario).strip() and str(r.nome).strip()
    ]
    with _conectar() as con:
        con.execute("DELETE FROM cobradores")
        con.executemany(
            "INSERT INTO cobradores (cod_usuario, nome, tipo, ativo) VALUES (?, ?, ?, ?)",
            linhas,
        )


# ------------------------------- ciclos -----------------------------------
def listar_ciclos() -> pd.DataFrame:
    with _conectar() as con:
        return pd.read_sql("SELECT id, mes, inicio, gerado_em FROM ciclos ORDER BY mes DESC", con)


def obter_ciclo(mes: str) -> dict | None:
    with _conectar() as con:
        row = con.execute(
            "SELECT id, mes, inicio, gerado_em FROM ciclos WHERE mes = ?", (mes,)
        ).fetchone()
    if row is None:
        return None
    return dict(zip(["id", "mes", "inicio", "gerado_em"], row, strict=True))


def _linhas_carteira(ciclo_id: int, df: pd.DataFrame, origem: str, agora: str) -> list:
    return [
        (
            ciclo_id,
            r.codcli,
            r.cod_usuario,
            r.loja_principal,
            int(r.prioridade),
            float(r.vl_vencido),
            float(r.vl_faixa),
            int(r.qt_titulos),
            int(r.dias_atraso_max),
            r.cliente,
            r.fantasia,
            r.telefone,
            r.whatsapp,
            origem,
            agora,
        )
        for r in df.itertuples()
    ]


_INSERT_CARTEIRA = """
    INSERT OR REPLACE INTO carteira
    (ciclo_id, codcli, cod_usuario, loja_principal, prioridade, vl_vencido_ini,
     vl_faixa_ini, qt_titulos_ini, dias_atraso_ini, cliente_ini, fantasia_ini,
     telefone_ini, whatsapp_ini, origem, entrou_em)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def salvar_ciclo(mes: str, inicio: str, distribuicao: pd.DataFrame) -> int:
    """Grava a carteira do mês. Se o mês já existia, ele é REFEITO do zero."""
    agora = datetime.now().isoformat(timespec="seconds")
    with _conectar() as con:
        con.execute("DELETE FROM ciclos WHERE mes = ?", (mes,))
        cur = con.execute(
            "INSERT INTO ciclos (mes, inicio, gerado_em) VALUES (?, ?, ?)",
            (mes, inicio, agora),
        )
        ciclo_id = cur.lastrowid
        con.executemany(
            _INSERT_CARTEIRA, _linhas_carteira(ciclo_id, distribuicao, "geracao", agora)
        )
    return ciclo_id


def adicionar_clientes(ciclo_id: int, distribuicao: pd.DataFrame, origem: str = "novo") -> None:
    agora = datetime.now().isoformat(timespec="seconds")
    with _conectar() as con:
        con.executemany(_INSERT_CARTEIRA, _linhas_carteira(ciclo_id, distribuicao, origem, agora))


def mover_cliente(ciclo_id: int, codcli: str, cod_usuario: str) -> None:
    """Troca manualmente o cobrador de um cliente."""
    with _conectar() as con:
        con.execute(
            "UPDATE carteira SET cod_usuario = ?, origem = 'manual' "
            "WHERE ciclo_id = ? AND codcli = ?",
            (cod_usuario, ciclo_id, codcli),
        )


def carteira_do_ciclo(ciclo_id: int) -> pd.DataFrame:
    with _conectar() as con:
        return pd.read_sql(
            "SELECT codcli, cod_usuario, loja_principal, prioridade, vl_vencido_ini, "
            "vl_faixa_ini, qt_titulos_ini, dias_atraso_ini, cliente_ini, fantasia_ini, "
            "telefone_ini, whatsapp_ini, origem, entrou_em "
            "FROM carteira WHERE ciclo_id = ?",
            con,
            params=(ciclo_id,),
        )
