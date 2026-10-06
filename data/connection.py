"""Camada de dados: conexão com o banco (réplica SIAC, somente leitura).

Usa st.connection, que mantém um POOL de conexões compartilhado entre todos os
usuários do app. Nunca abra conexão "na mão" (psycopg2.connect) no app.
"""

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # lê as credenciais do arquivo .env


def get_conn():
    """Devolve a conexão com pool (criada uma vez e reaproveitada)."""
    return st.connection(
        "siac",
        type="sql",
        dialect="postgresql",
        driver="psycopg2",  # obrigatório: o SQLAlchemy 2.1 tenta o psycopg 3 por padrão
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        pool_size=3,  # conexões mantidas abertas
        max_overflow=3,  # extras no pico → teto de 6 conexões para este app
        pool_timeout=30,  # espera até 30s por uma conexão livre
        pool_recycle=1800,  # recicla conexões com mais de 30 min
        pool_pre_ping=True,  # descarta conexões quebradas antes de usar
    )
