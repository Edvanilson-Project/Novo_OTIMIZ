#!/usr/bin/env python3
"""
══════════════════════════════════════════════════════════════════════════════
  OTIMIZ — STRESS TEST & AUDITORIA 360°
  Engenharia de Pesquisa Operacional · Sistemas de Transporte Público

  Restrições Hard auditadas:
    HW-01  Conflito de Veículo   : um ônibus em dois lugares ao mesmo tempo
    HW-02  Teletransporte        : origem ≠ destino anterior sem KM Morto
    HW-03  Layover Insuficiente  : intervalo < 10 min no mesmo terminal
    HW-04  Estouro de Jornada    : work_time > T_max (560 min)
    HW-05  Viagem Órfã           : ida sem volta correspondente no bloco
    HW-06  Bloco Indivisível     : par IDA/VOLTA separado entre veículos/drivers

  Restrições Soft auditadas:
    SW-01  Vácuo Operacional     : veículo parado > 45 min sem justificativa
    SW-02  Trabalho Mínimo CCT   : work_time < 240 min (CCT soft)
    SW-03  Adicional Noturno     : viagens entre 22h–05h sem flag de custo

  3 Iterações:
    Iter-1  Identificação de erros lógicos no dataset bruto
    Iter-2  Simulação de Efeito Cascata (+10 min de atraso na 1ª viagem de blocos críticos)
    Iter-3  Proposta de Otimização de Vácuos Operacionais

  Uso:
    cd /home/edvanilson/WEB_OPT/optimizer
    python tests/qa_exhaustive.py [--api] [--verbose]

══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sys
import time
import json
import requests
import argparse
import itertools
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ─── Tenta usar a API; se --api não for passado, roda offline ─────────────────
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES & CORES
# ══════════════════════════════════════════════════════════════════════════════

BASE_URL = "http://localhost:8000"

T_MAX             = 560   # minutos — CLT art.59  (440 base + 120 extras)
MIN_LAYOVER       = 10    # minutos — intervalo mínimo no terminal
MIN_WORK_SOFT     = 240   # minutos — CCT soft (4h)
VACUUM_THRESHOLD  = 45    # minutos — vácuo que justifica análise
NOCTURNAL_START   = 22 * 60  # 22:00 em minutos
NOCTURNAL_END     = 5  * 60  # 05:00 em minutos

RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

SEV_COLOR = {"CRÍTICO": RED + BOLD, "ALTO": YELLOW + BOLD, "MÉDIO": CYAN, "INFO": DIM}

# ══════════════════════════════════════════════════════════════════════════════
#  MODELOS DE DADOS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Terminal:
    id:   int
    name: str
    km_to: Dict[int, float] = field(default_factory=dict)  # term_id → km

@dataclass
class Trip:
    id:          int
    line_id:     int
    vehicle_id:  int
    driver_id:   int
    origin_id:   int
    dest_id:     int
    start:       int   # minutos desde meia-noite
    end:         int
    block_id:    int
    pair_id:     Optional[int] = None  # id do par IDA/VOLTA
    direction:   str  = "IDA"          # "IDA" ou "VOLTA"
    distance_km: float = 20.0
    line_name:   str  = ""             # nome original da linha (ex: "869I", "815VF")

    @property
    def duration(self) -> int:
        return self.end - self.start

    def hhmm_start(self) -> str:
        return _hhmm(self.start)

    def hhmm_end(self) -> str:
        return _hhmm(self.end)

@dataclass
class AuditError:
    severity:  str          # CRÍTICO / ALTO / MÉDIO / INFO
    code:      str          # HW-01, SW-01, etc.
    title:     str
    detail:    str
    trip_ids:  List[int] = field(default_factory=list)
    vehicle_id: Optional[int] = None
    driver_id:  Optional[int] = None

# ══════════════════════════════════════════════════════════════════════════════
#  TERMINAIS
# ══════════════════════════════════════════════════════════════════════════════

TERMINALS: Dict[int, Terminal] = {
    1: Terminal(1, "Terminal Parque/Garagem",    {2: 12.0, 3: 18.0, 4: 8.0}),
    2: Terminal(2, "Terminal Cachoeirinha",       {1: 12.0, 3: 10.0, 4: 15.0}),
    3: Terminal(3, "Terminal Jaraguá",            {1: 18.0, 2: 10.0, 4: 12.0}),
    4: Terminal(4, "Terminal Sul/URA",            {1: 8.0,  2: 15.0, 3: 12.0}),
}

KM_DEAD_SPEED_MIN_PER_KM = 2.0   # velocidade KM Morto: 30 km/h → 2 min/km

def deadhead_minutes(orig: int, dest: int) -> int:
    if orig == dest:
        return 0
    km = TERMINALS[orig].km_to.get(dest, 999.0)
    return int(km * KM_DEAD_SPEED_MIN_PER_KM)

# ══════════════════════════════════════════════════════════════════════════════
#  DATASET REAL — LINHAS 815/819/820/826/869/872/873
#
#  Mapeamento de terminais por prefixo de linha:
#    815x/869x : Terminal Parque (1) ↔ Terminal Cachoeirinha (2)
#    819x/872x : Terminal Cachoeirinha (2) ↔ Terminal Jaraguá (3)
#    820x      : Terminal Parque (1) ↔ Terminal Sul (4)
#    826x      : Terminal Sul (4) ↔ Terminal Jaraguá (3)
#    873x      : Terminal Jaraguá (3) ↔ Terminal Sul (4)
#
#  Coluna par_ida→volta: cada bloco (block_id) agrupa IDA e VOLTA da
#  mesma viagem; pair_id referencia o ID do viagem complementar.
#
#  Formato: (linha_nome, ida_ini, ida_fim, volta_ini, volta_fim)
#           volta_ini/volta_fim = None quando só há viagem de ida.
# ══════════════════════════════════════════════════════════════════════════════

def _m(hhmm: str) -> int:
    """Converte 'HH:MM' → minutos desde meia-noite. '' → 0."""
    if not hhmm:
        return 0
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m

_LINE_ID: Dict[str, int] = {
    "815": 815, "815VC": 815, "815VF": 815, "815IF": 815,
    "819I2": 819, "819IF": 819, "819IVF": 819, "819VFC": 819,
    "820": 820, "820IF": 820, "820VF": 820,
    "826A": 826, "826URA": 826, "826UVF": 826, "826B": 826,
    "869I": 869, "869IF": 869, "869IVF": 869, "869VFC": 869,
    "869VF2": 869, "869VF3": 869, "869I2": 869,
    "872": 872, "872TF": 872,
    "873A": 873,
}

_LINE_TERM: Dict[int, Tuple[int, int]] = {
    815: (1, 2),  819: (2, 3),  820: (1, 4),
    826: (4, 3),  869: (1, 2),  872: (2, 3),  873: (3, 4),
}

# Dados brutos: (linha, ida_ini, ida_fim, volta_ini_ou_"", volta_fim_ou_"")
_RAW: List[Tuple[str, str, str, str, str]] = [
    ("869I",   "09:40","10:35","10:35","11:25"),
    ("815VC",  "03:40","04:45","04:45","06:30"),
    ("819I2",  "12:40","13:34","13:34","14:38"),
    ("826A",   "17:45","19:25","19:25","20:45"),
    ("869IF",  "15:45","16:35","16:35","17:25"),
    ("869IVF", "06:36","07:28","07:28","08:19"),
    ("872",    "06:30","07:50","07:50","09:00"),
    ("820IF",  "16:20","17:30","17:30","18:40"),
    ("826A",   "19:00","20:30","20:30","21:50"),
    ("872TF",  "04:00","05:02","05:02","06:02"),
    ("815",    "19:30","20:50","20:50","22:00"),
    ("869I",   "17:30","18:30","18:30","19:20"),
    ("869I",   "22:25","23:15","23:15","23:55"),
    ("815VF",  "03:50","05:00","05:00","06:35"),
    ("819IF",  "15:15","16:05","16:05","17:15"),
    ("820",    "09:55","11:05","11:05","12:15"),
    ("815IF",  "15:40","17:30","17:30","19:26"),
    ("819I2",  "12:18","13:16","13:16","14:20"),
    ("819IVF", "06:24","07:20","07:20","08:35"),
    ("826URA", "03:45","04:50","",""),          # sem VOLTA
    ("869VFC", "05:10","06:14","",""),          # sem VOLTA
    ("869I",   "18:16","19:16","19:16","20:08"),
    ("815VF",  "04:00","05:20","05:20","07:00"),
    ("819I2",  "20:30","21:20","21:20","22:10"),
    ("869IF",  "16:20","17:14","17:14","18:05"),
    ("815",    "07:50","09:40","09:40","11:20"),
    ("820",    "12:30","13:38","13:38","14:48"),
    ("815VF",  "04:15","05:40","05:40","07:25"),
    ("826A",   "16:17","18:05","18:05","19:25"),
    ("819IVF", "04:15","05:00","05:00","06:10"),
    ("819IVF", "06:12","07:10","07:10","08:25"),
    ("869IF",  "16:10","17:04","17:04","18:06"),
    ("869I",   "11:45","12:37","12:37","13:27"),
    ("815IF",  "16:20","18:10","18:10","20:05"),
    ("819I2",  "08:36","09:31","09:31","10:32"),
    ("819I2",  "13:30","14:22","14:22","15:28"),
    ("869IVF", "06:12","07:10","07:10","08:04"),
    ("869VF2", "05:20","06:10","",""),          # sem VOLTA
    ("869VF3", "04:20","04:55","",""),          # sem VOLTA
    ("872",    "04:40","05:38","05:38","06:48"),
    ("872",    "09:35","10:45","10:45","12:00"),
    ("872",    "13:15","14:25","14:25","15:35"),
    ("872",    "16:00","17:20","17:20","18:40"),
    ("873A",   "07:15","08:25","08:25","09:20"),
    ("873A",   "19:20","20:20","20:20","21:20"),
    ("815",    "15:00","16:45","16:45","18:30"),
    ("819I2",  "09:36","10:31","10:31","11:31"),
    ("819I2",  "11:34","12:30","12:30","13:32"),
    ("819IVF", "04:30","05:15","05:15","06:15"),
    ("869IVF", "06:24","07:20","07:20","08:10"),
    ("815VF",  "04:30","06:00","06:00","07:45"),
    ("873A",   "16:35","17:55","17:55","19:05"),
    ("815",    "17:28","19:15","19:15","20:43"),
    ("869I",   "12:35","13:27","13:27","14:17"),
    ("820",    "08:50","10:00","10:00","11:10"),
    ("819I2",  "21:35","22:15","22:15","23:00"),
    ("826A",   "14:20","15:55","15:55","17:15"),
    ("826UVF", "04:35","06:05","06:05","07:25"),
    ("820VF",  "04:38","05:33","05:33","06:41"),
    ("826A",   "15:00","16:42","16:42","18:10"),
    ("869IVF", "06:48","07:44","07:44","08:35"),
    ("869I",   "12:10","13:02","13:02","13:52"),
    ("819I2",  "10:06","11:01","11:01","12:01"),
    ("819IVF", "06:36","07:30","07:30","08:45"),
    ("826A",   "15:20","17:02","17:02","18:30"),
    ("869VF2", "05:35","06:30","",""),          # sem VOLTA
    ("869VF3", "04:40","05:30","",""),          # sem VOLTA
    ("872",    "15:00","16:15","16:15","17:25"),
    ("826URA", "04:40","05:50","",""),          # sem VOLTA
    ("869IVF", "07:00","08:00","08:00","08:50"),
    ("869VF2", "06:08","07:00","",""),          # sem VOLTA
    ("872",    "07:35","08:53","08:53","10:09"),
    ("872",    "11:00","12:10","12:10","13:25"),
    ("872",    "14:25","15:40","15:40","16:50"),
    ("872",    "17:30","18:50","18:50","20:10"),
    ("873A",   "05:00","05:58","05:58","06:50"),
    ("815",    "09:40","11:20","11:20","13:05"),
    ("815",    "14:30","16:10","16:10","18:00"),
    ("819IVF", "04:45","05:30","05:30","06:30"),
    ("820VF",  "06:30","07:40","07:40","08:50"),
    ("815VF",  "04:45","06:20","06:20","08:05"),
    ("869IF",  "16:05","17:20","17:20","18:12"),
    ("815",    "13:50","15:30","15:30","17:20"),
    ("820",    "11:20","12:30","12:30","13:40"),
    ("826UVF", "04:55","06:25","06:25","07:45"),
    ("869I",   "08:50","09:45","09:45","10:35"),
    ("869I",   "17:40","18:40","18:40","19:30"),
    ("820",    "17:42","18:45","18:45","19:40"),
    ("815VF",  "05:00","06:40","06:40","08:30"),
    ("819IF",  "15:30","16:20","16:20","17:30"),
    ("815IF",  "15:20","17:10","17:10","19:01"),
    ("819IVF", "05:00","05:45","05:45","06:53"),
    ("819IVF", "07:00","07:59","07:59","09:06"),
    ("815",    "10:35","12:15","12:15","14:00"),
    ("815VF",  "07:00","08:50","08:50","10:37"),
    ("819I2",  "11:56","12:50","12:50","13:52"),
    ("869IF",  "15:15","16:05","16:05","16:55"),
    ("869IF",  "17:00","18:00","18:00","18:50"),
    ("869VF2", "05:50","06:40","",""),          # sem VOLTA
    ("869VF3", "05:00","05:40","",""),          # sem VOLTA
    ("869IVF", "05:12","06:00","06:00","06:50"),
    ("819I2",  "18:00","19:00","19:00","20:10"),
    ("819IVF", "05:12","06:02","06:02","07:10"),
    ("820IF",  "15:38","16:48","16:48","17:58"),
    ("869I",   "10:30","11:22","11:22","12:13"),
    ("869I",   "13:24","14:14","14:14","15:05"),
    ("869IVF", "07:20","08:20","08:20","09:17"),
    ("819IF",  "15:45","16:35","16:35","17:50"),
    ("826UVF", "05:15","06:50","06:50","08:10"),
    ("869I",   "17:50","18:50","18:50","19:41"),
    ("872",    "05:30","06:47","06:47","08:05"),
    ("872",    "08:20","09:38","09:38","10:48"),
    ("872",    "12:10","13:20","13:20","14:30"),
    ("872",    "15:30","16:45","16:45","18:05"),
    ("872",    "18:30","19:35","19:35","20:45"),
    ("872",    "21:35","22:35","22:35","23:35"),
    ("815VF",  "05:15","07:05","07:05","08:55"),
    ("819IF",  "16:24","17:20","17:20","18:30"),
    ("815",    "12:10","13:50","13:50","15:30"),
    ("869I",   "09:15","10:10","10:10","11:00"),
    ("869I",   "18:32","19:32","19:32","20:22"),
    ("819I2",  "15:00","15:50","15:50","16:53"),
    ("819IVF", "07:22","08:19","08:19","09:27"),
    ("826A",   "10:50","12:20","12:20","13:45"),
    ("826A",   "17:15","18:55","18:55","20:20"),
    ("869I2",  "05:16","06:24","",""),          # sem VOLTA
    ("869VF2", "06:24","07:18","",""),          # sem VOLTA
    ("819I2",  "14:30","15:22","15:22","16:25"),
    ("826A",   "08:20","09:55","09:55","11:15"),
    ("869I",   "11:20","12:12","12:12","13:02"),
    ("869IF",  "16:50","17:49","17:49","18:39"),
    ("869IVF", "05:24","06:16","06:16","07:10"),
    ("820",    "07:30","08:40","08:40","09:50"),
    ("820",    "13:50","15:00","15:00","16:10"),
    ("815IF",  "17:00","18:50","18:50","20:38"),
    ("819IVF", "05:24","06:14","06:14","07:20"),
    ("819VFC", "05:23","06:23","06:23","07:35"),
    ("826A",   "14:40","16:21","16:21","17:50"),
    ("815VF",  "05:30","07:25","07:25","09:15"),
    ("819I2",  "10:36","11:31","11:31","12:31"),
    ("819IF",  "16:36","17:35","17:35","18:45"),
    ("815",    "13:00","14:35","14:35","16:15"),
    ("869I",   "18:48","19:48","19:48","20:40"),
    ("819I2",  "13:05","13:55","13:55","15:00"),
    ("819IF",  "17:00","18:00","18:00","19:10"),
    ("819IVF", "07:44","08:39","08:39","09:44"),
    ("820VF",  "05:30","06:30","06:30","07:35"),
    ("869I",   "10:05","11:00","11:00","11:50"),
    ("869I",   "15:00","15:50","15:50","16:40"),
    ("869I",   "19:15","20:09","20:09","20:56"),
    ("815VF",  "06:25","08:15","08:15","10:05"),
    ("819IF",  "16:00","16:50","16:50","18:00"),
    ("826B",   "05:35","06:15","",""),          # sem VOLTA
    ("815",    "11:25","13:05","13:05","14:47"),
    ("869I",   "18:00","19:00","19:00","19:50"),
    ("872",    "17:00","18:20","18:20","19:40"),
    ("872",    "20:15","21:15","21:15","22:20"),
    ("869IVF", "05:36","06:32","06:32","07:24"),
    ("819I2",  "17:33","18:30","18:30","19:40"),
    ("819I2",  "19:40","20:30","20:30","21:30"),
    ("819IVF", "05:36","06:30","06:30","07:40"),
    ("826A",   "13:40","15:15","15:15","16:40"),
    ("826UVF", "05:40","07:15","07:15","08:35"),
    ("869I",   "13:48","14:38","14:38","15:28"),
    ("869IF",  "15:30","16:20","16:20","17:10"),
    ("869IF",  "17:20","18:20","18:20","19:05"),
    ("819IF",  "17:16","18:15","18:15","19:25"),
    ("873A",   "06:00","07:19","07:19","08:27"),
    ("819I2",  "14:00","14:53","14:53","15:57"),
    ("819I2",  "19:00","19:50","19:50","20:50"),
    ("819IF",  "16:48","17:47","17:47","18:57"),
    ("869I",   "10:55","11:47","11:47","12:37"),
    ("869IVF", "05:48","06:40","06:40","07:32"),
    ("869IVF", "07:40","08:40","08:40","09:30"),
    ("815IF",  "16:40","18:30","18:30","20:25"),
    ("819IVF", "05:48","06:40","06:40","07:52"),
    ("819IVF", "08:06","09:01","09:01","10:02"),
    ("869I",   "20:45","21:29","21:29","22:15"),
    ("869I",   "08:00","09:00","09:00","09:50"),
    ("869I2",  "05:45","07:00","",""),          # sem VOLTA
    ("869IF",  "16:00","16:50","16:50","17:40"),
    ("869VF2", "07:00","07:55","",""),          # sem VOLTA
    ("819IF",  "16:12","17:05","17:05","18:15"),
    ("819VFC", "05:47","06:50","06:50","08:00"),
    ("815VF",  "05:55","07:50","07:50","09:40"),
    ("819I2",  "11:06","12:01","12:01","13:02"),
    ("819I2",  "18:30","19:20","19:20","20:20"),
    ("869I",   "14:12","15:02","15:02","15:52"),
    ("869IF",  "16:40","17:38","17:38","18:28"),
    ("826A",   "16:00","17:44","17:44","19:10"),
    ("869I",   "08:25","09:20","09:20","10:10"),
    ("869IVF", "06:00","06:50","06:50","07:45"),
    ("819IVF", "06:00","07:00","07:00","08:12"),
    ("826A",   "16:50","18:30","18:30","19:55"),
    ("869I",   "14:36","15:26","15:26","16:16"),
    ("869I",   "20:00","20:44","20:44","21:30"),
    ("819IVF", "06:48","07:40","07:40","08:55"),
    ("820IF",  "16:42","17:52","17:52","19:01"),
    ("826B",   "06:05","06:40","",""),          # sem VOLTA
    ("820VF",  "06:06","07:12","07:12","08:22"),
    ("826A",   "16:18","17:22","17:22","18:50"),
    ("815",    "08:45","10:30","10:30","12:15"),
    ("815",    "18:00","19:37","19:37","21:05"),
    ("869I",   "13:00","13:50","13:50","14:40"),
    ("820",    "14:50","16:00","16:00","17:10"),
    ("826UVF", "06:15","07:55","07:55","09:15"),
    ("869IF",  "17:10","18:10","18:10","19:00"),
    ("819I2",  "09:06","10:01","10:01","11:01"),
    ("826A",   "12:30","14:00","14:00","15:25"),
    ("815",    "18:40","20:00","20:00","21:10"),
    ("869I",   "21:30","22:20","22:20","23:00"),
    ("869I2",  "06:25","07:36","",""),          # sem VOLTA
    ("869IF",  "16:30","17:26","17:26","18:18"),
    ("869VF2", "07:36","08:26","",""),          # sem VOLTA
]

# ── Construção do dataset a partir dos dados brutos ───────────────────────────

def _build_trips() -> Tuple[List[Trip], Dict[int, Dict]]:
    """
    Gera a lista de Trip separando VSP (veículo) de CSP (motorista).

    ── VSP — Vehicle Scheduling Problem ────────────────────────────────────
      Veículos não têm limite de jornada — um ônibus roda do início ao fim
      do dia. Resultado: MENOS veículos (30-45).
      Regra de reutilização:
        · Se último terminal == próximo terminal → gap ≥ MIN_LAYOVER (10 min)
        · Se terminais diferentes → gap ≥ deadhead_time(from, to)

    ── CSP — Crew Scheduling Problem ────────────────────────────────────────
      Motoristas respeitam T_max = 560 min (CLT art.59).
      Jornada = último_fim − primeiro_início (para o motorista).
      Um motorista pode trocar de veículo (rendição) mas não pode
      ultrapassar T_max em nenhum cenário.
      Resultado: MAIS motoristas que veículos (cada veículo precisa de
      1-2 motoristas por dia).

    TRIP_PAIRS[block_id] = {
        "linha", "ida_id", "volta_id", "ida_horario", "volta_horario",
        "layover_min", "vehicle_id", "driver_id"
    }
    """
    DEADHEAD_SPEED_KMH = 20.0

    def _dh_gap(term_from: int, term_to: int) -> int:
        """Gap mínimo (min) entre dois terminais."""
        if term_from == term_to:
            return MIN_LAYOVER          # mesmo terminal → respeita layover
        dist = TERMINALS.get(term_from, Terminal(0, "", {})).km_to.get(term_to, 15.0)
        return max(MIN_LAYOVER, int(dist / DEADHEAD_SPEED_KMH * 60))

    # ── Passo 1: montar todos os blocos ordenados por i_start ────────────────
    all_blocks = []
    for block_id, (lname, ii, if_, vi, vf) in enumerate(_RAW, start=1):
        lid        = _LINE_ID.get(lname, 0)
        orig, dest = _LINE_TERM.get(lid, (1, 2))
        i_start    = _m(ii); i_end = _m(if_)
        v_start    = _m(vi); v_end = _m(vf)
        has_volta  = bool(vi)
        block_end  = v_end if has_volta else i_end
        end_term   = orig  if has_volta else dest
        all_blocks.append({
            "block_id": block_id, "lname": lname,
            "ii": ii, "if_": if_, "vi": vi, "vf": vf,
            "i_start": i_start, "i_end": i_end,
            "v_start": v_start, "v_end": v_end,
            "has_volta": has_volta, "block_end": block_end,
            "orig": orig, "dest": dest, "end_term": end_term,
        })
    all_blocks.sort(key=lambda b: b["i_start"])

    # ── Passo 2: VSP — atribuição de VEÍCULOS (sem limite de jornada) ────────
    # pool: (free_at, last_terminal, vehicle_id)
    next_veh   = 1
    block_veh: Dict[int, int] = {}
    veh_pool: List[Tuple[int, int, int]] = []

    for b in all_blocks:
        best_idx  = None
        best_free = -1
        for idx, (free_at, last_term, vid) in enumerate(veh_pool):
            gap = _dh_gap(last_term, b["orig"])
            if free_at + gap <= b["i_start"]:
                # Prefere veículo que fica livre mais tarde + mesmo terminal
                priority = (free_at, 0 if last_term == b["orig"] else 1)
                if best_idx is None or free_at > best_free or \
                   (free_at == best_free and last_term == b["orig"]):
                    best_idx  = idx
                    best_free = free_at
        if best_idx is not None:
            _, _, vid = veh_pool.pop(best_idx)
        else:
            vid = next_veh
            next_veh += 1
        block_veh[b["block_id"]] = vid
        veh_pool.append((b["block_end"], b["end_term"], vid))

    # ── Passo 3: CSP — atribuição de MOTORISTAS (com T_max = 560 min) ────────
    # pool: (shift_start, last_end, last_terminal, driver_id)
    next_drv   = 1
    block_drv: Dict[int, int] = {}
    drv_pool: List[Tuple[int, int, int, int]] = []

    for b in all_blocks:
        block_dur = b["block_end"] - b["i_start"]
        best_idx  = None
        best_end  = -1
        for idx, (shift_start, last_end, last_term, did) in enumerate(drv_pool):
            gap          = _dh_gap(last_term, b["orig"])
            new_shift_end = b["block_end"]
            new_jornada   = new_shift_end - shift_start
            if (last_end + gap <= b["i_start"]           # sem sobreposição + deadhead
                    and new_jornada <= T_MAX):            # CLT art.59
                # Prefere motorista que terminou mais tarde (maximiza aproveitamento)
                if best_idx is None or last_end > best_end or \
                   (last_end == best_end and last_term == b["orig"]):
                    best_idx = idx
                    best_end = last_end
        if best_idx is not None:
            shift_start, _, _, did = drv_pool.pop(best_idx)
        else:
            shift_start = b["i_start"]
            did = next_drv
            next_drv += 1
        block_drv[b["block_id"]] = did
        drv_pool.append((shift_start, b["block_end"], b["end_term"], did))

    # ── Passo 4: construir trips com vehicle_id e driver_id separados ────────
    trips: List[Trip] = []
    pairs: Dict[int, Dict] = {}

    for block_id, (lname, ii, if_, vi, vf) in enumerate(_RAW, start=1):
        lid        = _LINE_ID.get(lname, 0)
        orig, dest = _LINE_TERM.get(lid, (1, 2))
        ida_id     = block_id * 2 - 1
        volta_id   = block_id * 2
        vehicle_id = block_veh[block_id]
        driver_id  = block_drv[block_id]

        i_start   = _m(ii); i_end = _m(if_)
        v_start   = _m(vi); v_end = _m(vf)
        has_volta = bool(vi)
        dist_km   = round((i_end - i_start) / 60 * 30, 1)

        trips.append(Trip(
            id=ida_id, line_id=lid, vehicle_id=vehicle_id, driver_id=driver_id,
            origin_id=orig, dest_id=dest,
            start=i_start, end=i_end, block_id=block_id,
            pair_id=volta_id if has_volta else None,
            direction="IDA", distance_km=dist_km, line_name=lname,
        ))
        if has_volta:
            dist_v = round((v_end - v_start) / 60 * 30, 1)
            trips.append(Trip(
                id=volta_id, line_id=lid, vehicle_id=vehicle_id, driver_id=driver_id,
                origin_id=dest, dest_id=orig,
                start=v_start, end=v_end, block_id=block_id,
                pair_id=ida_id,
                direction="VOLTA", distance_km=dist_v, line_name=lname,
            ))

        pairs[block_id] = {
            "linha":          lname,
            "ida_id":         ida_id,
            "volta_id":       volta_id if has_volta else None,
            "ida_horario":    f"{ii}→{if_}",
            "volta_horario":  f"{vi}→{vf}" if has_volta else "—",
            "layover_min":    (v_start - i_end) if has_volta else None,
            "vehicle_id":     vehicle_id,
            "driver_id":      driver_id,
        }

    return trips, pairs


TRIPS, TRIP_PAIRS = _build_trips()


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════════════════

def _hhmm(mins: int) -> str:
    sign = ""
    if mins < 0:
        sign, mins = "-", -mins
    return f"{sign}{mins//60:02d}:{mins%60:02d}"

def _sev_badge(sev: str) -> str:
    return f"{SEV_COLOR.get(sev, '')}[{sev}]{RESET}"

def _trips_by_vehicle() -> Dict[int, List[Trip]]:
    res: Dict[int, List[Trip]] = {}
    for t in TRIPS:
        res.setdefault(t.vehicle_id, []).append(t)
    for v in res:
        res[v].sort(key=lambda t: t.start)
    return res

def _trips_by_driver() -> Dict[int, List[Trip]]:
    res: Dict[int, List[Trip]] = {}
    for t in TRIPS:
        res.setdefault(t.driver_id, []).append(t)
    for d in res:
        res[d].sort(key=lambda t: t.start)
    return res

def _trips_by_block() -> Dict[int, List[Trip]]:
    res: Dict[int, List[Trip]] = {}
    for t in TRIPS:
        res.setdefault(t.block_id, []).append(t)
    return res

def _work_time(trips: List[Trip]) -> int:
    return sum(t.duration for t in trips)

def _spread_time(trips: List[Trip]) -> int:
    if not trips:
        return 0
    return trips[-1].end - trips[0].start

# ══════════════════════════════════════════════════════════════════════════════
#  ITER-1 — IDENTIFICAÇÃO DE ERROS LÓGICOS
# ══════════════════════════════════════════════════════════════════════════════

def audit_iter1() -> List[AuditError]:
    errors: List[AuditError] = []
    by_veh    = _trips_by_vehicle()
    by_driver = _trips_by_driver()
    by_block  = _trips_by_block()

    # ── HW-01: Conflito de veículo ────────────────────────────────────────────
    for vid, trips in by_veh.items():
        for i in range(len(trips) - 1):
            a, b = trips[i], trips[i+1]
            if a.end > b.start:   # sobreposição
                errors.append(AuditError(
                    severity="CRÍTICO", code="HW-01",
                    title="Conflito de Veículo — Sobreposição de Horário",
                    detail=(f"VEH-{vid}: Viagem #{a.id} termina às {a.hhmm_end()} "
                            f"mas Viagem #{b.id} já inicia às {b.hhmm_start()} "
                            f"(sobreposição de {a.end - b.start} min)"),
                    trip_ids=[a.id, b.id], vehicle_id=vid,
                ))

    # ── HW-02: Teletransporte ─────────────────────────────────────────────────
    for vid, trips in by_veh.items():
        for i in range(len(trips) - 1):
            a, b = trips[i], trips[i+1]
            if a.dest_id == b.origin_id:
                continue   # mesmo terminal — sem KM morto
            required   = deadhead_minutes(a.dest_id, b.origin_id)
            available  = b.start - a.end
            if available < required:
                short = required - available
                errors.append(AuditError(
                    severity="CRÍTICO", code="HW-02",
                    title="Teletransporte — KM Morto Insuficiente",
                    detail=(f"VEH-{vid}: de T{a.dest_id}({TERMINALS[a.dest_id].name}) "
                            f"→ T{b.origin_id}({TERMINALS[b.origin_id].name}) "
                            f"exige {required} min de deslocamento, "
                            f"disponível={available} min | falta {short} min"),
                    trip_ids=[a.id, b.id], vehicle_id=vid,
                ))

    # ── HW-03: Layover insuficiente ───────────────────────────────────────────
    for vid, trips in by_veh.items():
        for i in range(len(trips) - 1):
            a, b = trips[i], trips[i+1]
            if a.dest_id != b.origin_id:
                continue   # terminais diferentes → capturado em HW-02
            layover = b.start - a.end
            if 0 < layover < MIN_LAYOVER:
                errors.append(AuditError(
                    severity="ALTO", code="HW-03",
                    title="Layover Insuficiente no Terminal",
                    detail=(f"VEH-{vid}: entre #{a.id}→#{b.id} no T{a.dest_id}"
                            f"({TERMINALS[a.dest_id].name}): "
                            f"layover={layover} min < mín={MIN_LAYOVER} min"),
                    trip_ids=[a.id, b.id], vehicle_id=vid,
                ))

    # ── HW-04: Estouro de jornada ─────────────────────────────────────────────
    for did, trips in by_driver.items():
        work   = _work_time(trips)
        spread = _spread_time(trips)
        if spread > T_MAX:
            errors.append(AuditError(
                severity="CRÍTICO", code="HW-04",
                title="Estouro de Jornada (CLT art.59)",
                detail=(f"DRIVER-{did}: spread={spread} min ({_hhmm(spread)}) "
                        f"> T_max={T_MAX} min ({_hhmm(T_MAX)}) "
                        f"| excesso de {spread - T_MAX} min"),
                trip_ids=[t.id for t in trips], driver_id=did,
            ))

    # ── HW-05: Viagem órfã ────────────────────────────────────────────────────
    for bid, trips in by_block.items():
        idas   = [t for t in trips if t.direction == "IDA"]
        voltas = [t for t in trips if t.direction == "VOLTA"]
        for ida in idas:
            paired = any(v.pair_id == ida.id or ida.pair_id == v.id for v in voltas)
            if not paired:
                errors.append(AuditError(
                    severity="ALTO", code="HW-05",
                    title="Viagem Órfã — IDA sem VOLTA correspondente",
                    detail=(f"Bloco-{bid}: Viagem #{ida.id} "
                            f"(L{ida.line_id} {TERMINALS[ida.origin_id].name}→"
                            f"{TERMINALS[ida.dest_id].name}) "
                            f"não tem VOLTA no mesmo bloco. "
                            f"Veículo retorna em local incorreto ao fim do dia."),
                    trip_ids=[ida.id], vehicle_id=ida.vehicle_id,
                ))

    # ── HW-06: Bloco indivisível violado (par IDA/VOLTA com drivers distintos) ─
    for bid, trips in by_block.items():
        for t in trips:
            if t.pair_id is None:
                continue
            pair_trip = next((x for x in TRIPS if x.id == t.pair_id), None)
            if pair_trip is None:
                continue
            if t.driver_id != pair_trip.driver_id and t.direction == "IDA":
                errors.append(AuditError(
                    severity="CRÍTICO", code="HW-06",
                    title="Bloco Indivisível Violado — Driver muda dentro do par",
                    detail=(f"Bloco-{bid}: par #{t.id}(IDA,DR-{t.driver_id}) / "
                            f"#{pair_trip.id}(VOLTA,DR-{pair_trip.driver_id}) "
                            f"têm motoristas DIFERENTES sem rendição planejada"),
                    trip_ids=[t.id, pair_trip.id], vehicle_id=t.vehicle_id,
                ))

    # ── SW-01: Vácuo operacional ──────────────────────────────────────────────
    for vid, trips in by_veh.items():
        for i in range(len(trips) - 1):
            a, b = trips[i], trips[i+1]
            vacuum = b.start - a.end
            if vacuum > VACUUM_THRESHOLD:
                errors.append(AuditError(
                    severity="MÉDIO", code="SW-01",
                    title="Vácuo Operacional Excessivo",
                    detail=(f"VEH-{vid}: veículo parado {vacuum} min "
                            f"entre #{a.id}(até {a.hhmm_end()}) e "
                            f"#{b.id}(a partir {b.hhmm_start()}) "
                            f"— candidato a realocação ou inserção de viagem extra"),
                    trip_ids=[a.id, b.id], vehicle_id=vid,
                ))

    # ── SW-02: Trabalho mínimo CCT ────────────────────────────────────────────
    for did, trips in by_driver.items():
        work = _work_time(trips)
        if 0 < work < MIN_WORK_SOFT:
            errors.append(AuditError(
                severity="MÉDIO", code="SW-02",
                title="Trabalho Abaixo do Mínimo CCT (soft)",
                detail=(f"DRIVER-{did}: work_time={work} min ({_hhmm(work)}) "
                        f"< mínimo CCT={MIN_WORK_SOFT} min ({_hhmm(MIN_WORK_SOFT)})"),
                trip_ids=[t.id for t in trips], driver_id=did,
            ))

    # ── SW-03: Adicional noturno não sinalizado ───────────────────────────────
    for t in TRIPS:
        is_noct = (t.start >= NOCTURNAL_START) or (t.end <= NOCTURNAL_END + 60)
        if is_noct:
            errors.append(AuditError(
                severity="MÉDIO", code="SW-03",
                title="Viagem Noturna sem Custo de Adicional",
                detail=(f"Viagem #{t.id} (L{t.line_id} "
                        f"{t.hhmm_start()}→{t.hhmm_end()}) "
                        f"cobre período noturno CLT art.73 "
                        f"(+20% custo não contabilizado)"),
                trip_ids=[t.id], driver_id=t.driver_id,
            ))

    return errors

# ══════════════════════════════════════════════════════════════════════════════
#  ITER-2 — EFEITO CASCATA (+10 min na 1ª viagem de blocos com conflito)
# ══════════════════════════════════════════════════════════════════════════════

def simulate_cascade(errors: List[AuditError], delay_min: int = 10) -> List[dict]:
    """Aplica +N min ao início das viagens críticas e calcula o efeito em cadeia."""
    critical_trips = set()
    for e in errors:
        if e.severity == "CRÍTICO":
            critical_trips.update(e.trip_ids)

    # Identifica 1ª viagem de cada veículo afetado
    affected_vehs: Dict[int, List[Trip]] = {}
    for t in TRIPS:
        if t.id in critical_trips:
            affected_vehs.setdefault(t.vehicle_id, []).append(t)

    cascade_log = []
    for vid, trips in affected_vehs.items():
        trips_sorted = sorted(trips, key=lambda x: x.start)
        first = trips_sorted[0]
        all_veh_trips = sorted(
            [t for t in TRIPS if t.vehicle_id == vid], key=lambda x: x.start
        )
        # Propaga o atraso cumulativamente
        running_delay = delay_min
        chain = []
        for t in all_veh_trips:
            if t.start >= first.start:
                new_start = t.start + running_delay
                new_end   = t.end   + running_delay
                orig_layover = 0
                if chain:
                    prev = chain[-1]
                    orig_layover  = t.start - prev["orig_end"]
                    new_layover   = new_start - prev["new_end"]
                    if new_layover < MIN_LAYOVER and orig_layover >= MIN_LAYOVER:
                        running_delay += max(0, MIN_LAYOVER - new_layover)
                        new_start = t.start + running_delay
                        new_end   = t.end   + running_delay
                chain.append({
                    "trip_id":       t.id,
                    "orig_start":    t.start,
                    "orig_end":      t.end,
                    "new_start":     new_start,
                    "new_end":       new_end,
                    "delay_acum":    running_delay,
                    "layover_ok":    True if not chain else (new_start - chain[-1]["new_end"]) >= MIN_LAYOVER,
                })
        total_extra_delay = chain[-1]["delay_acum"] if chain else 0
        cascade_log.append({
            "vehicle_id":          vid,
            "first_delayed_trip":  first.id,
            "initial_delay_min":   delay_min,
            "trips_affected":      len(chain),
            "total_acum_delay":    total_extra_delay,
            "chain":               chain,
        })
    return cascade_log

# ══════════════════════════════════════════════════════════════════════════════
#  ITER-3 — PROPOSTA DE OTIMIZAÇÃO DE VÁCUOS OPERACIONAIS
# ══════════════════════════════════════════════════════════════════════════════

def propose_vacuum_optimization() -> List[dict]:
    """Sugere ações para preencher vácuos operacionais detectados."""
    by_veh = _trips_by_vehicle()
    proposals = []
    for vid, trips in by_veh.items():
        for i in range(len(trips) - 1):
            a, b = trips[i], trips[i+1]
            vacuum = b.start - a.end
            if vacuum <= VACUUM_THRESHOLD:
                continue
            # Verifica se há demanda na linha deste veículo nesse janelo
            slots_in_vacuum = [
                t for t in TRIPS
                if t.line_id == a.line_id
                and a.end <= t.start < b.start
                and t.vehicle_id != vid
            ]
            km_dead = deadhead_minutes(a.dest_id, b.origin_id) if a.dest_id != b.origin_id else 0
            proposals.append({
                "vehicle_id":     vid,
                "vacuum_start":   a.end,
                "vacuum_end":     b.start,
                "vacuum_min":     vacuum,
                "after_trip":     a.id,
                "before_trip":    b.id,
                "terminal":       TERMINALS[a.dest_id].name,
                "viable_window":  vacuum - km_dead,
                "existing_trips_same_window": len(slots_in_vacuum),
                "recommendation": (
                    "INSERIR viagem extra" if vacuum >= 60 and km_dead <= 5
                    else "REPOSICIONAR veículo para apoio em outra linha"
                    if km_dead < vacuum * 0.5
                    else "Vácuo estrutural — considerar redução de headway"
                ),
            })
    return proposals

# ══════════════════════════════════════════════════════════════════════════════
#  RELATÓRIOS DE SAÍDA
# ══════════════════════════════════════════════════════════════════════════════

def print_header(iteration: int, title: str):
    w = 76
    print(f"\n{BOLD}{'═'*w}{RESET}")
    sep = f"  ITER-{iteration} — {title}"
    print(f"{BOLD}{sep:<{w}}{RESET}")
    print(f"{BOLD}{'═'*w}{RESET}")

def print_error_table(errors: List[AuditError], verbose: bool = False):
    sev_order = {"CRÍTICO": 0, "ALTO": 1, "MÉDIO": 2, "INFO": 3}
    sorted_errs = sorted(errors, key=lambda e: sev_order.get(e.severity, 9))

    # Sumário
    from collections import Counter
    counts = Counter(e.severity for e in sorted_errs)
    print(f"\n  {'─'*72}")
    print(f"  {'SEVERIDADE':<12}  {'QTD':>5}  {'CÓDIGO':>7}  TÍTULO")
    print(f"  {'─'*72}")

    last_sev = None
    for e in sorted_errs:
        badge = _sev_badge(e.severity)
        vid_info   = f" VEH-{e.vehicle_id}" if e.vehicle_id else ""
        did_info   = f" DR-{e.driver_id}"   if e.driver_id  else ""
        who = vid_info or did_info
        print(f"  {badge:<25} {e.code:<8} {e.title}")
        if verbose or e.severity == "CRÍTICO":
            wrapped = textwrap.fill(e.detail, width=68,
                                    initial_indent="           ↳ ",
                                    subsequent_indent="             ")
            print(f"{DIM}{wrapped}{RESET}")
            if e.trip_ids:
                print(f"{DIM}             Viagens: {e.trip_ids}{RESET}")

    print(f"\n  {'─'*72}")
    print(f"  TOTAIS: ", end="")
    for sev in ["CRÍTICO", "ALTO", "MÉDIO"]:
        c = counts.get(sev, 0)
        print(f"{SEV_COLOR.get(sev,'')}{sev}: {c}{RESET}  ", end="")
    print()

def print_cascade_report(cascade: List[dict]):
    print(f"\n  Delay inicial aplicado: +10 min à 1ª viagem de cada veículo crítico")
    print(f"  {'─'*72}")
    for c in cascade:
        print(f"\n  VEH-{c['vehicle_id']} — viagem inicial afetada: #{c['first_delayed_trip']}")
        print(f"  Viagens em cadeia impactadas: {c['trips_affected']}")
        print(f"  Atraso acumulado ao fim: {c['total_acum_delay']} min")
        print(f"  {'─'*40}")
        print(f"  {'#VIAGEM':>8}  {'ORIG':>8}  {'NOVA':>8}  {'ΔMIN':>5}  {'LAYOVER_OK':>10}")
        for row in c["chain"]:
            ok_sym = f"{GREEN}✓{RESET}" if row["layover_ok"] else f"{RED}✗{RESET}"
            print(f"  {row['trip_id']:>8}  "
                  f"{_hhmm(row['orig_start']):>8}  "
                  f"{_hhmm(row['new_start']):>8}  "
                  f"{row['delay_acum']:>5}  "
                  f"      {ok_sym}")

def print_vacuum_proposals(proposals: List[dict]):
    if not proposals:
        print(f"\n  {GREEN}Nenhum vácuo operacional acima de {VACUUM_THRESHOLD} min detectado.{RESET}")
        return
    print(f"\n  {'─'*72}")
    print(f"  {'VEH':>5}  {'INÍCIO':>7}  {'FIM':>7}  {'MIN':>5}  {'JANELA_ÚTIL':>12}  RECOMENDAÇÃO")
    print(f"  {'─'*72}")
    total_vacuum = sum(p["vacuum_min"] for p in proposals)
    for p in proposals:
        print(f"  {p['vehicle_id']:>5}  "
              f"{_hhmm(p['vacuum_start']):>7}  "
              f"{_hhmm(p['vacuum_end']):>7}  "
              f"{p['vacuum_min']:>5}  "
              f"{p['viable_window']:>12}  "
              f"{p['recommendation']}")
    print(f"\n  Total de minutos ociosos acima do limiar: {BOLD}{total_vacuum} min{RESET} "
          f"({_hhmm(total_vacuum)} h)")

def print_summary_table(errors: List[AuditError]):
    """Tabela final de registros que precisam de correção imediata."""
    critical = [e for e in errors if e.severity in ("CRÍTICO", "ALTO")]
    if not critical:
        print(f"\n  {GREEN}✓ Nenhum erro crítico ou alto. Dataset aprovado.{RESET}")
        return
    print(f"\n  {BOLD}{'─'*76}{RESET}")
    print(f"  {BOLD}{'CÓDIGO':<9}{'SEV':<10}{'TRIP_IDS':<18}{'VEH/DR':<10}AÇÃO IMEDIATA{RESET}")
    print(f"  {'─'*76}")
    for e in critical:
        sev_disp = f"{SEV_COLOR.get(e.severity,'')}{e.severity}{RESET}"
        who = f"VEH-{e.vehicle_id}" if e.vehicle_id else (f"DR-{e.driver_id}" if e.driver_id else "—")
        action = {
            "HW-01": "Remanejar viagem ou inserir veículo extra",
            "HW-02": "Adicionar KM Morto ou alinhar terminal de origin",
            "HW-03": "Ampliar layover ou atrasar partida da trip seguinte",
            "HW-04": "Dividir jornada ou realocar viagens > T_max",
            "HW-05": "Inserir viagem de VOLTA ou reclassificar como 'fim de bloco'",
            "HW-06": "Inserir ponto de rendição ou manter mesmo driver no par",
        }.get(e.code, "Revisar manualmente")
        ids_str = str(e.trip_ids[:4]) + ("…" if len(e.trip_ids) > 4 else "")
        print(f"  {e.code:<9}{sev_disp:<20}{ids_str:<18}{who:<10}{action}")

# ══════════════════════════════════════════════════════════════════════════════
#  TABELA DE PARES IDA↔VOLTA
# ══════════════════════════════════════════════════════════════════════════════

def print_pairs_table(pairs: Dict) -> None:
    """Exibe a associação IDA↔VOLTA de cada bloco operacional."""
    print(f"\n  {BOLD}{'─'*96}{RESET}")
    print(f"  {BOLD}{'BLK':>5}  {'VEH':>5}  {'LINHA':<10} {'IDA_ID':>7}  {'IDA_HOR':>12}  "
          f"{'VOLTA_ID':>9}  {'VOLTA_HOR':>12}  {'LAYOVER':>8}{RESET}")
    print(f"  {'─'*96}")
    for bid, p in sorted(pairs.items()):
        v_id  = str(p["volta_id"])    if p["volta_id"]    is not None else "—"
        v_hor = p["volta_horario"]    if p["volta_horario"]            else "—"
        lay   = f"{p['layover_min']}min" if p["layover_min"] is not None else "—"
        lay_color = (YELLOW if p["layover_min"] == 0
                     else (RED if (p["layover_min"] is not None and p["layover_min"] < MIN_LAYOVER)
                           else GREEN)) if p["layover_min"] is not None else ""
        veh_str = str(p.get("vehicle_id", "?"))
        print(f"  {bid:>5}  {veh_str:>5}  {p['linha']:<10} {p['ida_id']:>7}  {p['ida_horario']:>12}  "
              f"{v_id:>9}  {v_hor:>12}  {lay_color}{lay:>8}{RESET}")
    total_pares = sum(1 for p in pairs.values() if p["volta_id"] is not None)
    total_solo  = sum(1 for p in pairs.values() if p["volta_id"] is None)
    veh_uniq    = len(set(p.get("vehicle_id") for p in pairs.values()))
    print(f"  {'─'*96}")
    print(f"  Total: {BOLD}{len(pairs)}{RESET} blocos  |  "
          f"{GREEN}{total_pares} pares IDA↔VOLTA{RESET}  |  "
          f"{YELLOW}{total_solo} viagens só IDA{RESET}  |  "
          f"{CYAN}{veh_uniq} veículos/motoristas únicos{RESET}")

# ══════════════════════════════════════════════════════════════════════════════
#  INTEGRAÇÃO API (OPCIONAL)
# ══════════════════════════════════════════════════════════════════════════════

def _api_alive(timeout: int = 4) -> bool:
    """Verifica se o optimizer está respondendo."""
    try:
        r = requests.get(f"{BASE_URL}/health/", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def run_api_validation(errors: List[AuditError]) -> None:
    """
    Valida o dataset com TODOS os algoritmos disponíveis:
      CSP  : greedy, set_partitioning
      VSP  : genetic, simulated_annealing, tabu_search
      INTEGR: joint_solver
      HYBRID: hybrid_pipeline
    """
    if not _HAS_REQUESTS:
        print(f"  {YELLOW}requests não instalado — pulando validação via API.{RESET}")
        return
    if not _api_alive():
        print(f"  {YELLOW}Optimizer offline — pulando validação API.{RESET}")
        return

    # Monta payload base (sem trips com erros CRÍTICO)
    critical_ids: set = set()
    for e in errors:
        if e.severity == "CRÍTICO":
            critical_ids.update(e.trip_ids)
    clean_trips = [t for t in TRIPS if t.id not in critical_ids]
    base_trips = [
        {"id": t.id, "line_id": t.line_id,
         "start_time": t.start, "end_time": t.end,
         "origin_id": t.origin_id, "destination_id": t.dest_id,
         "duration": t.duration, "distance_km": t.distance_km}
        for t in clean_trips
    ]
    cct = {
        "max_shift_minutes":      T_MAX,
        "overtime_limit_minutes": 120,
        "min_layover_minutes":    MIN_LAYOVER,
        "nocturnal_start_hour":   22,
        "nocturnal_end_hour":     5,
        "nocturnal_extra_pct":    0.20,
        "apply_cct":              True,
    }

    # Nomes válidos conforme /health: greedy, genetic, simulated_annealing,
    # tabu_search, set_partitioning, joint_solver, hybrid_pipeline
    # timeout: rápidos=60s | lentos (budget interno 300s) usam 360s
    ALGORITHMS = [
        ("greedy",               "CSP   greedy",              60),
        ("set_partitioning",     "CSP   set_partitioning",    60),
        ("genetic",              "VSP   genetic",             60),
        ("simulated_annealing",  "VSP   simulated_annealing", 60),
        ("tabu_search",          "VSP   tabu_search",        360),
        ("joint_solver",         "INTEGR joint_solver",      360),
        ("hybrid_pipeline",      "HYBRID hybrid_pipeline",   360),
    ]

    def _restart_api() -> bool:
        import subprocess as _sp
        _sp.run(["pkill","-f","uvicorn main:app"], capture_output=True)
        time.sleep(2)
        _sp.Popen(
            [".venv/bin/uvicorn","main:app","--host","0.0.0.0","--port","8000",
             "--log-level","warning"],
            stdout=open("/tmp/uvicorn.log","a"), stderr=_sp.STDOUT
        )
        for _ in range(12):
            time.sleep(2)
            if _api_alive(): return True
        return False

    print(f"\n  Enviando {len(clean_trips)} viagens limpas ({len(critical_ids)} excluídas).")
    print(f"  {'ALGORITMO':<32} {'STATUS':>7}  {'CREW':>6}  {'CCT_VIOL':>9}  "
          f"{'UNASSIGNED':>11}  {'TEMPO':>7}")
    print(f"  {'─'*74}")

    results = {}
    for algo, label, tmt in ALGORITHMS:
        payload = {"trips": base_trips, "algorithm": algo, "cct_params": cct}
        try:
            # Verifica se API está viva antes de cada chamada; reinicia se caiu
            if not _api_alive(timeout=5):
                print(f"  {label:<32} {YELLOW}⚠ reiniciando API...{RESET}", flush=True)
                if not _restart_api():
                    print(f"  {label:<32} {RED}✗ API não subiu{RESET}")
                    results[algo] = None
                    continue
            t0   = time.time()
            with open("/tmp/exhaust_payload.json", "w") as f: json.dump(payload, f)
            resp = requests.post(f"{BASE_URL}/optimize/", json=payload, timeout=tmt)
            dt   = time.time() - t0
            if resp.status_code == 200:
                d = resp.json()
                ok = d.get("cct_violations", 0) == 0 and d.get("unassigned_trips", 0) == 0
                sym = f"{GREEN}✓ OK   {RESET}" if ok else f"{YELLOW}⚠ WARN {RESET}"
                print(f"  {label:<32} {sym}  {d.get('crew',0):>6}  "
                      f"{d.get('cct_violations',0):>9}  "
                      f"{d.get('unassigned_trips',0):>11}  "
                      f"{dt:>6.2f}s", flush=True)
                results[algo] = d
            else:
                err_msg = str(resp.json().get('detail', resp.text))[:120] if resp.text else ''
                print(f"  {label:<32} {RED}✗ HTTP {resp.status_code}{RESET}  {err_msg}", flush=True)
                results[algo] = None
        except Exception as exc:
            print(f"  {label:<32} {RED}✗ Erro{RESET}: {repr(exc)[:150]}", flush=True)
            results[algo] = None

    # Resumo comparativo
    ok_count  = sum(1 for v in results.values() if v and
                    v.get('cct_violations', 0) == 0 and v.get('unassigned_trips', 0) == 0)
    total     = len(ALGORITHMS)
    sym_total = GREEN + BOLD if ok_count == total else (YELLOW + BOLD if ok_count > 0 else RED + BOLD)
    print(f"  {'─'*74}")
    print(f"  {sym_total}{ok_count}/{total} algoritmos sem violações{RESET}")

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="OTIMIZ — Stress Test & Auditoria 360° de Programação Horária"
    )
    parser.add_argument("--api",     action="store_true", help="Chamar API após auditoria")
    parser.add_argument("--verbose", action="store_true", help="Mostrar detalhe de todos erros")
    parser.add_argument("--json",    action="store_true", help="Exportar erros em JSON")
    parser.add_argument("--pairs",   action="store_true", help="Exibir tabela de associação IDA↔VOLTA")
    args = parser.parse_args()

    print(f"\n{BOLD}{'█'*76}{RESET}")
    print(f"{BOLD}  OTIMIZ — STRESS TEST EXAUSTIVO & AUDITORIA 360°{RESET}")
    print(f"{BOLD}  Pesquisa Operacional · Transporte Público Urbano · {time.strftime('%d/%m/%Y %H:%M')}{RESET}")
    print(f"{BOLD}{'█'*76}{RESET}")
    n_veh = len(set(t.vehicle_id for t in TRIPS))
    n_drv = len(set(t.driver_id  for t in TRIPS))
    print(f"\n  Dataset: {len(TRIPS)} viagens · "
          f"{n_veh} veículos (VSP) · "
          f"{n_drv} motoristas (CSP) · "
          f"{len(set(t.line_id for t in TRIPS))} linhas · "
          f"{len(set(t.block_id for t in TRIPS))} blocos")
    if n_drv <= n_veh:
        print(f"  {YELLOW}⚠ Motoristas ≤ Veículos: esperado motoristas > veículos (cada veículo usa 1-2 turnos/dia){RESET}")
    else:
        print(f"  {GREEN}✓ VSP/CSP correto: {n_drv} motoristas > {n_veh} veículos{RESET}")
    print(f"  T_max = {T_MAX} min ({_hhmm(T_MAX)})  |  "
          f"Layover_min = {MIN_LAYOVER} min  |  "
          f"Vácuo_threshold = {VACUUM_THRESHOLD} min")

    # ── TABELA DE PARES IDA↔VOLTA ─────────────────────────────────────────────
    if args.pairs:
        print(f"\n{BOLD}{'═'*76}{RESET}")
        print(f"{BOLD}  ASSOCIAÇÃO IDA↔VOLTA POR BLOCO OPERACIONAL{RESET}")
        print(f"{BOLD}{'═'*76}{RESET}")
        print_pairs_table(TRIP_PAIRS)

    # ── ITER-1 ────────────────────────────────────────────────────────────────
    print_header(1, "IDENTIFICAÇÃO DE ERROS LÓGICOS")
    errors = audit_iter1()
    print_error_table(errors, verbose=args.verbose)
    print_summary_table(errors)

    # ── ITER-2 ────────────────────────────────────────────────────────────────
    print_header(2, f"SIMULAÇÃO DE EFEITO CASCATA (+10 min nos blocos críticos)")
    cascade = simulate_cascade(errors, delay_min=10)
    if cascade:
        print_cascade_report(cascade)
    else:
        print(f"\n  {GREEN}Nenhum bloco crítico com viagens encadeadas para simular.{RESET}")

    # ── ITER-3 ────────────────────────────────────────────────────────────────
    print_header(3, "PROPOSTA DE OTIMIZAÇÃO — VÁCUOS OPERACIONAIS")
    proposals = propose_vacuum_optimization()
    print_vacuum_proposals(proposals)

    # ── VALIDAÇÃO API ─────────────────────────────────────────────────────────
    if args.api:
        print_header(0, "VALIDAÇÃO CRUZADA VIA API OTIMIZ")
        run_api_validation(errors)

    # ── EXPORT JSON ──────────────────────────────────────────────────────────
    if args.json:
        import json

        out = {
            "dataset_trips": len(TRIPS),
            "errors": [
                {"severity": e.severity, "code": e.code, "title": e.title,
                 "detail": e.detail, "trip_ids": e.trip_ids}
                for e in errors
            ],
            "cascade": cascade,
            "vacuum_proposals": proposals,
        }
        path = "/tmp/audit_report.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n  {GREEN}✓ Relatório JSON exportado para {path}{RESET}")

    # ── PLACAR FINAL ──────────────────────────────────────────────────────────
    from collections import Counter
    counts = Counter(e.severity for e in errors)
    crit   = counts.get("CRÍTICO", 0)
    alto   = counts.get("ALTO",    0)
    medio  = counts.get("MÉDIO",   0)

    print(f"\n{BOLD}{'═'*76}{RESET}")
    print(f"{BOLD}  RESULTADO FINAL DA AUDITORIA{RESET}")
    print(f"  {RED+BOLD}CRÍTICO: {crit:>3}{RESET}   "
          f"{YELLOW+BOLD}ALTO: {alto:>3}{RESET}   "
          f"{CYAN}MÉDIO: {medio:>3}{RESET}")
    status = "REPROVADO" if crit > 0 else ("ATENÇÃO" if alto > 0 else "APROVADO")
    color  = RED+BOLD if crit > 0 else (YELLOW+BOLD if alto > 0 else GREEN+BOLD)
    print(f"\n  Status: {color}{status}{RESET}")
    print(f"{BOLD}{'═'*76}{RESET}\n")
    return 0 if crit == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
