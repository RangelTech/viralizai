"""Banco do Viralizaí: SQLite num volume (/data). Hora sempre em epoch (s)."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  criado REAL NOT NULL,
  plano TEXT NOT NULL DEFAULT 'teste',      -- teste | corte | animacao | viral | piloto
  ativo_ate REAL NOT NULL DEFAULT 0,
  pedido TEXT,
  nome TEXT, whatsapp TEXT,
  estilo TEXT,                               -- JSON: redes, arrobas, cor, moldura, legenda, selfie
  moedas INTEGER NOT NULL DEFAULT 0,         -- vídeo com IA (1 moeda = 1 vídeo de 10 s)
  adicionais TEXT,                           -- JSON: {"cacador": ate, "vigia": ate}
  temas TEXT,                                -- JSON: ["gta", "podcast"]
  onboarding INTEGER NOT NULL DEFAULT 0,
  teste_usado INTEGER NOT NULL DEFAULT 0,    -- a prévia grátis (1 corte) já foi usada
  origem TEXT                                -- fael | rangel (landing de entrada)
);
CREATE TABLE IF NOT EXISTS codigos (
  email TEXT PRIMARY KEY, hash TEXT NOT NULL, expira REAL NOT NULL, tentativas INTEGER NOT NULL DEFAULT 0, enviado REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes (hash TEXT PRIMARY KEY, usuario INTEGER NOT NULL, expira REAL NOT NULL);
CREATE TABLE IF NOT EXISTS trabalhos (
  id TEXT PRIMARY KEY,
  usuario INTEGER NOT NULL,
  tipo TEXT NOT NULL,                          -- cortes | vitrine | animacao | video_ia | editar
  entrada TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'fila',         -- fila | rodando | montando | pronto | erro
  etapa TEXT NOT NULL DEFAULT '',
  progresso REAL NOT NULL DEFAULT 0,
  resultado TEXT,
  erro TEXT,
  criado REAL NOT NULL,
  fim REAL,
  fonte TEXT,                                  -- chave do vídeo (cache)
  prioridade INTEGER NOT NULL DEFAULT 5        -- menor = antes (plano)
);
CREATE INDEX IF NOT EXISTS trab_usuario ON trabalhos(usuario, criado);
CREATE INDEX IF NOT EXISTS trab_estado ON trabalhos(estado, prioridade, criado);
-- montagem de cada corte de um pedido: fila justa (todo mundo recebe o 1º antes de alguém receber o 3º)
CREATE TABLE IF NOT EXISTS tarefas (
  id INTEGER PRIMARY KEY,
  trabalho TEXT NOT NULL,
  k INTEGER NOT NULL,                          -- posição do corte no pedido (1, 2, 3...)
  corte_base INTEGER,
  dados TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'fila',         -- fila | rodando | pronto | erro
  prioridade INTEGER NOT NULL DEFAULT 5,
  criado REAL NOT NULL,
  tentativas INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tarefa_fila ON tarefas(estado, k, prioridade, criado);
-- cache absoluto: cada vídeo analisado uma vez
CREATE TABLE IF NOT EXISTS fontes (
  chave TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  titulo TEXT, canal TEXT, duracao REAL, capa TEXT, tipo TEXT, plataforma TEXT,
  publica INTEGER NOT NULL DEFAULT 1,          -- upload do cliente = 0 (nunca vai para a vitrine)
  estado TEXT NOT NULL DEFAULT 'nova',
  criado REAL NOT NULL,
  analisada REAL
);
-- cortes base (sem marca de ninguém): o que aparece em "Prontos pra postar"
CREATE TABLE IF NOT EXISTS cortes_base (
  id INTEGER PRIMARY KEY,
  fonte TEXT NOT NULL,
  objetivo TEXT NOT NULL,
  inicio REAL NOT NULL, fim REAL NOT NULL,
  nota INTEGER NOT NULL, porque TEXT, gancho TEXT, titulo TEXT, legenda TEXT, hashtags TEXT, assunto TEXT, tipo TEXT,
  tema TEXT,
  capa TEXT, previa TEXT,                      -- caminhos no cache da fonte
  publico INTEGER NOT NULL DEFAULT 1,
  oculto INTEGER NOT NULL DEFAULT 0,           -- moderação no admin
  usos INTEGER NOT NULL DEFAULT 0,
  criado REAL NOT NULL,
  UNIQUE(fonte, inicio, fim)
);
CREATE INDEX IF NOT EXISTS base_vitrine ON cortes_base(publico, oculto, nota);
CREATE TABLE IF NOT EXISTS usos (corte_base INTEGER NOT NULL, usuario INTEGER NOT NULL, quando REAL NOT NULL);
CREATE INDEX IF NOT EXISTS usos_dia ON usos(corte_base, quando);
CREATE TABLE IF NOT EXISTS moedas_mov (id INTEGER PRIMARY KEY, usuario INTEGER NOT NULL, delta INTEGER NOT NULL, motivo TEXT, ref TEXT, quando REAL NOT NULL);
CREATE TABLE IF NOT EXISTS avisos (id INTEGER PRIMARY KEY, usuario INTEGER NOT NULL, texto TEXT NOT NULL, link TEXT, lido INTEGER NOT NULL DEFAULT 0, quando REAL NOT NULL);
CREATE INDEX IF NOT EXISTS avisos_u ON avisos(usuario, lido, quando);
CREATE TABLE IF NOT EXISTS eventos_cakto (id TEXT PRIMARY KEY, recebido REAL NOT NULL, corpo TEXT NOT NULL);
"""


class Banco:
    def __init__(self, caminho: str):
        self.caminho = caminho
        self._trava = threading.RLock()
        self.con = sqlite3.connect(caminho, check_same_thread=False, isolation_level=None, timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript(ESQUEMA)

    @contextmanager
    def tx(self):
        with self._trava:
            self.con.execute("BEGIN IMMEDIATE")
            try:
                yield self.con
                self.con.execute("COMMIT")
            except BaseException:
                self.con.execute("ROLLBACK")
                raise

    def um(self, sql: str, args=()):
        with self._trava:
            r = self.con.execute(sql, args).fetchone()
        return dict(r) if r else None

    def todos(self, sql: str, args=()):
        with self._trava:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def exec(self, sql: str, args=()):
        with self._trava:
            return self.con.execute(sql, args)


def agora() -> float:
    return time.time()
