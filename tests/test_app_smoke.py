"""Teste de fumaça: abre as telas com o banco SIAC simulado (sem rede)."""

import random
from datetime import date, timedelta

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
from data.queries import contatos as q_contatos
from data.queries import titulos as q_titulos
from tests.conftest import RAIZ

HOJE = date.today()
COBS = ["8177", "3522", "8526", "2281", "4366", "4369"]


@pytest.fixture
def siac_falso(monkeypatch, tmp_path, clientes):
    monkeypatch.setattr(config, "CAMINHO_BANCO_CARTEIRA", str(tmp_path / "carteira.db"))
    monkeypatch.setattr(config, "GESTOR_SENHA", "segredo")
    base = clientes.to_pandas()
    base["cliente"] = "CLIENTE " + base["codcli"]
    base["fantasia"] = None
    base["telefone"] = "61 33330000"
    base["whatsapp"] = "61 999990000"
    base["telefones"] = "61999990000,6133330000"
    base["qt_faixa"] = 1
    base["dias_atraso_max"] = 30
    base["lojas"] = base["loja_principal"]
    base["email"] = None

    monkeypatch.setattr(q_titulos, "clientes_elegiveis", lambda: base.copy())
    monkeypatch.setattr(
        q_titulos,
        "situacao_atual",
        lambda codigos: base[base["codcli"].isin(codigos) & (base.index % 10 != 0)].copy(),
    )
    monkeypatch.setattr(
        q_titulos,
        "recuperado_na_faixa",
        lambda codigos, datas: pd.DataFrame(
            {"codcli": list(codigos)[:20], "qt_pagos": 1, "vl_recuperado": 100.0}
        ),
    )

    def contatos(inicio, codigos):
        rnd = random.Random(1)  # mesmo resultado a cada rerun
        linhas = [
            {
                "codcli": c,
                "dt_cobran": HOJE - timedelta(days=rnd.randint(1, 5)),
                "hr_cobran": "10:00:00",
                "cd_usuario": rnd.choice(COBS),
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
                "ult_data": HOJE - timedelta(days=1),
                "ult_hora": "10:00:00",
                "ult_usuario": "8177",
                "ult_resultado": "TELEFONE NAO ATENDE",
                "ult_texto": "mandei msg no zap",
                "prox_ligacao": HOJE,
            }
        ),
    )
    monkeypatch.setattr(
        q_contatos,
        "historico_cliente",
        lambda codcli, dias=120: pd.DataFrame(
            {
                "data": [HOJE],
                "hora": ["10:00:00"],
                "cd_usuario": ["8177"],
                "loja": ["Gama"],
                "resultado": ["EM NEGOCIACAO"],
                "anotacao": ["ok"],
                "valor_cobrado": [100.0],
                "prox_ligacao": [HOJE],
            }
        ),
    )
    monkeypatch.setattr(
        q_contatos,
        "usuarios_que_cobraram",
        lambda dias=30: pd.DataFrame(
            {"cd_usuario": COBS, "ligacoes": 10, "clientes": 5, "ultima_ligacao": HOJE}
        ),
    )
    monkeypatch.setattr(
        q_contatos,
        "tipos_negociacao",
        lambda: pd.DataFrame(
            {"cd_negocia": ["04", "11"], "ds_negocia": ["TELEFONE NAO ATENDE", "EM NEGOCIACAO"]}
        ),
    )


def _app(perfil=None, cod=None):
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60)
    if perfil:
        at.session_state["perfil"] = perfil
        at.session_state["cod_usuario"] = cod
        at.session_state["nome_usuario"] = "teste"
    at.run()
    assert not at.exception, at.exception
    return at


def test_login_e_perfis(siac_falso):
    from data import carteira_store
    from domain import servico

    # Sem login: só a tela de entrar
    at = _app()
    assert at.radio[0].options == ["Sou cobrador(a)", "Sou gestor(a)"]

    # Gestor com senha errada / certa
    at.radio[0].set_value("Sou gestor(a)").run()
    at.text_input[0].set_value("errada").run()
    at.button[0].click().run()
    assert any("incorreta" in e.value for e in at.error)
    at.text_input[0].set_value("segredo").run()
    at.button[0].click().run()
    assert at.session_state["perfil"] == "gestor"

    carteira_store.inicializar()
    servico.gerar_carteira(servico.mes_atual(), HOJE)

    # Gestor: todas as telas abrem
    for pagina in ("visao_geral", "carteira_cobrador", "gerar", "cobradores"):
        at = _app("gestor", "GESTOR")
        at.switch_page(f"views/{pagina}.py").run()
        assert not at.exception, (pagina, at.exception)

    # Cobrador: abre direto na carteira dele, sem escolher outro cobrador
    at = _app("cobrador", "8177")
    assert "Minha carteira" in at.title[0].value
    assert not [s for s in at.selectbox if s.label == "Cobrador"]
    assert at.metric[0].label == "Meus clientes"

    # Para o cobrador, as telas de gestão nem existem na navegação
    with pytest.raises(ValueError, match="Could not find a navigation page"):
        at.switch_page("views/gerar.py")


def test_rotina_e_anotacao(siac_falso):
    from data import carteira_store
    from domain import servico

    carteira_store.inicializar()
    servico.gerar_carteira(servico.mes_atual(), HOJE)

    at = _app("cobrador", "3522")
    gerar = next(b for b in at.button if "Gerar rotina" in b.label)
    gerar.click().run()
    assert not at.exception, at.exception
    rotina = carteira_store.rotina_do_dia("3522", HOJE.isoformat())
    assert len(rotina) == config.ROTINA_TAMANHO_PADRAO

    # Escreve uma anotação no 1º cliente da rotina
    cli = rotina[0]
    at.text_area(key=f"txt_rot_{cli}").set_value("Falei com o dono, paga sexta.")
    at.selectbox(key=f"res_rot_{cli}").set_value("11")
    form_btn = next(b for b in at.button if b.label == "💾 Salvar anotação")
    form_btn.click().run()
    assert not at.exception, at.exception
    notas = carteira_store.anotacoes([cli])
    assert notas.iloc[0]["texto"] == "Falei com o dono, paga sexta."
    assert notas.iloc[0]["cod_usuario"] == "3522"
    # agora o cliente conta como contatado hoje
    assert cli in servico.contatados_hoje(carteira_store.obter_ciclo(servico.mes_atual()))
