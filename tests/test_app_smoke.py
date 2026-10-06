"""Teste de fumaça: abre todas as telas com o banco SIAC simulado (sem rede)."""

import random
from datetime import date, timedelta

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
from data.queries import contatos as q_contatos
from data.queries import titulos as q_titulos
from tests.conftest import RAIZ


@pytest.fixture
def siac_falso(monkeypatch, tmp_path, clientes):
    monkeypatch.setattr(config, "CAMINHO_BANCO_CARTEIRA", str(tmp_path / "carteira.db"))
    base = clientes.to_pandas()
    base["cliente"] = "CLIENTE " + base["codcli"]
    base["fantasia"] = None
    base["telefone"] = "61 3333-0000"
    base["whatsapp"] = "61 99999-0000"
    base["qt_faixa"] = 1
    base["dias_atraso_max"] = 30
    base["lojas"] = base["loja_principal"]
    base["email"] = None

    monkeypatch.setattr(q_titulos, "clientes_elegiveis", lambda: base.copy())

    def situacao(codigos):
        # 10% dos clientes "pagaram tudo"
        return base[base["codcli"].isin(codigos) & (base.index % 10 != 0)].copy()

    monkeypatch.setattr(q_titulos, "situacao_atual", situacao)
    cods = ["8177", "4366", "2281", "3522", "4369", "8526"]

    def contatos(inicio, codigos):
        rnd = random.Random(1)  # mesmo resultado a cada rerun
        linhas = [
            {
                "codcli": c,
                "dt_cobran": date.today() - timedelta(days=rnd.randint(0, 5)),
                "hr_cobran": "10:00:00",
                "cd_usuario": rnd.choice(cods),
                "cd_negocia": rnd.choice(["04", "12", "11", "02"]),
            }
            for c in codigos
            for _ in range(rnd.randint(0, 7))
        ]
        return pd.DataFrame(linhas)

    monkeypatch.setattr(q_contatos, "contatos_no_ciclo", contatos)
    monkeypatch.setattr(
        q_contatos,
        "ultimo_contato",
        lambda codigos: pd.DataFrame(
            {
                "codcli": list(codigos),
                "ult_data": date.today(),
                "ult_hora": "10:00:00",
                "ult_usuario": "8177",
                "ult_resultado": "TELEFONE NAO ATENDE",
                "ult_texto": "mandei msg no zap",
                "prox_ligacao": date.today() + timedelta(days=1),
            }
        ),
    )
    monkeypatch.setattr(
        q_contatos,
        "historico_cliente",
        lambda codcli, dias=120: pd.DataFrame(
            {
                "data": [date.today()],
                "hora": ["10:00"],
                "cd_usuario": ["8177"],
                "loja": ["Gama"],
                "resultado": ["EM NEGOCIACAO"],
                "anotacao": ["ok"],
                "valor_cobrado": [100.0],
                "prox_ligacao": [date.today()],
            }
        ),
    )
    monkeypatch.setattr(
        q_contatos,
        "usuarios_que_cobraram",
        lambda dias=30: pd.DataFrame(
            {
                "cd_usuario": cods,
                "ligacoes": 10,
                "clientes": 5,
                "ultima_ligacao": date.today(),
            }
        ),
    )


def _rodar(pagina):
    at = AppTest.from_file(str(RAIZ / pagina), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_fluxo_completo(siac_falso):
    from data import carteira_store
    from domain import servico

    carteira_store.inicializar()
    # Sem carteira: telas mostram aviso
    at = _rodar("views/visao_geral.py")
    assert any("Ainda não existe carteira" in i.value for i in at.info)

    # Gerar: prévia e salvar
    at = _rodar("views/gerar.py")
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert any("151 clientes" in s.value for s in at.success)
    servico.gerar_carteira(servico.mes_atual(), date.today())

    for pagina in (
        "views/visao_geral.py",
        "views/carteira_cobrador.py",
        "views/gerar.py",
        "views/cobradores.py",
    ):
        at = _rodar(pagina)

    at = _rodar("views/carteira_cobrador.py")
    assert at.metric[0].value  # "Meus clientes"
    sb = next(sb for sb in at.selectbox if sb.label == "Cliente")
    sb.set_value(sb.options[0].split(" · ")[0]).run()
    assert not at.exception, at.exception
    assert len(at.dataframe) == 2  # carteira + histórico
    assert not at.exception, at.exception
