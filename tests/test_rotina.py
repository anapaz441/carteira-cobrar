from datetime import datetime

import polars as pl

from domain import progresso
from domain.rotina import selecionar_rotina


def test_rotina_prioriza_sem_contato_e_mais_antigos():
    df = pl.DataFrame(
        {
            "codcli": ["a", "b", "c", "d", "e"],
            "status": [
                progresso.STATUS_ANDAMENTO,
                progresso.STATUS_SEM_CONTATO,
                progresso.STATUS_ANDAMENTO,
                progresso.STATUS_REGULARIZADO,
                progresso.STATUS_ANDAMENTO,
            ],
            "contatos": [1, 0, 1, 0, 1],
            "ult_quando": [
                datetime(2026, 10, 5),
                None,
                datetime(2026, 10, 1),
                None,
                datetime(2026, 10, 2),
            ],
            "prioridade": [1, 7, 2, 1, 1],
            "vl_faixa": [10.0, 5.0, 3.0, 100.0, 50.0],
        }
    )
    # "e" já teve contato hoje; "d" está regularizado
    assert selecionar_rotina(df, {"e"}, 10) == ["b", "c", "a"]
    assert selecionar_rotina(df, set(), 2) == ["b", "c"]
