"""Dados de teste: os 151 clientes reais da faixa 16–60 dias em 06/10/2026 (sem nomes)."""

import sys
from pathlib import Path

import polars as pl
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


@pytest.fixture
def clientes() -> pl.DataFrame:
    return pl.read_csv(
        RAIZ / "tests/fixtures/clientes_2026-10-06.csv",
        separator=";",
        schema_overrides={"codcli": pl.Utf8, "loja_principal": pl.Utf8},
    )


@pytest.fixture
def cobradores() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_usuario": ["A", "B", "C", "D", "E", "F"],
            "nome": ["Ana", "Bia", "Caio", "Dani", "Edu", "Fabi"],
            "tipo": ["Integral"] * 3 + ["Parcial"] * 3,
        }
    )
