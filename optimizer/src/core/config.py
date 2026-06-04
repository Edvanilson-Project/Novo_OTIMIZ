"""Configuração central via variáveis de ambiente (Pydantic BaseSettings)."""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

OPTIMIZER_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(OPTIMIZER_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="allow",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_version: str = "2.0.0"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"

    # ── Algoritmos habilitados ────────────────────────────────────────────────
    enabled_algorithms: List[str] = Field(
        default=[
            "greedy",
            "genetic",
            "simulated_annealing",
            "tabu_search",
            "set_partitioning",
            "joint_solver",
            "hybrid_pipeline",
        ]
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: List[str] = Field(default=["http://localhost:3000", "http://localhost:3001"])

    # ── Database (PostgreSQL async) ───────────────────────────────────────────
    db_host: str = Field(default="postgres", validation_alias="DB_HOST")
    db_port: int = Field(default=5432, validation_alias="DB_PORT")
    db_database: str = Field(default="otimiz_db", validation_alias="DB_NAME")
    db_username: str = Field(default="otimiz_admin", validation_alias="DB_USER")
    db_password: str = Field(default="otimiz_password", validation_alias="DB_PASSWORD")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_database}"
        )

    # ── Backend NestJS (notificações de status) ───────────────────────────────
    backend_url: str = Field(default="http://backend:3001/api/v1", validation_alias="BACKEND_URL")
    backend_secret: str = Field(default="", validation_alias="BACKEND_SECRET")

    # ── Estratégia (persistência + reconciliação) ────────────────────────────
    strategy_data_dir: str = "./data/strategy"
    strategy_auto_reconcile_enabled: bool = True
    strategy_reconcile_interval_seconds: int = 300
    strategy_feed_inbox_dir: str = "./data/strategy/inbox"
    strategy_feed_archive_dir: str = "./data/strategy/archive"
    strategy_feed_poll_interval_seconds: int = 30
    strategy_feed_auto_reconcile_on_ingest: bool = True
    strategy_retention_max_scenarios: int = 500
    strategy_retention_max_feed_snapshots: int = 2000
    strategy_retention_max_reports: int = 2000
    strategy_retention_max_age_days: int = 90
    strategy_retention_cleanup_interval_seconds: int = 600

    # ── Limites computacionais ────────────────────────────────────────────────
    # Genetic Algorithm
    ga_population_size: int = 200
    ga_generations: int = 500
    ga_mutation_rate: float = 0.1
    ga_elite_size: int = 15

    # Simulated Annealing
    sa_initial_temp: float = 5000.0
    sa_cooling_rate: float = 0.997
    sa_min_temp: float = 0.1
    sa_iterations_per_temp: int = 50
    sa_max_iterations: int = 10000

    # Tabu Search
    ts_tabu_size: int = 30
    ts_max_iterations: int = 5000
    ts_neighborhood_size: int = 40

    # ILP timeout (segundos) e paralelismo
    ilp_timeout_seconds: int = 120
    ilp_threads: int = 8

    # Hybrid pipeline: tempo máximo total (segundos)
    hybrid_time_budget_seconds: int = 900

    # ── Custos padrão (quando tipo de veículo não fornece custo) ──────────────
    default_vehicle_fixed_cost: float = 800.0  # R$ por veículo por dia
    default_cost_per_km: float = 2.0  # R$ por km
    default_cost_per_hour: float = 50.0  # R$ por hora de operação

    # ── Regras CCT (Convenção Coletiva de Trabalho) ───────────────────────────
    # max_shift_minutes: amplitude total da jornada (1ª viagem → última) — spread.
    #   Valor 560 min (9h20) é padrão de CCTs regionais (ex: SP, Salvador).
    #   NÃO é valor da CLT — a CLT define trabalho efetivo (8h), não spread.
    #   Fonte: CCTs sindicais regionais (SINTUR, SINDPASS, SINTTRONORMAT, etc.)
    cct_max_shift_minutes: int = 560  # 9h20 de spread/amplitude (CCT regional)

    # max_work_minutes: trabalho efetivo máximo (tempo realmente ao volante).
    #   Fonte: CLT Art. 235-C, caput (Lei 13.103/2015) — 8h de jornada efetiva.
    cct_max_work_minutes: int = 480  # 8h de trabalho efetivo (CLT Art. 235-C)

    # max_driving_minutes: condução contínua máxima antes de pausa obrigatória.
    #   CTB Art. 67-C §1-A: pausa de 30min a cada 4h de condução (passageiros).
    #   CTB Art. 67-C, caput: máximo absoluto contínuo = 5h30 (330min).
    #   O valor 270min (4h30) é conservador/CCT — mais restritivo que os 4h do CTB.
    #   Use mandatory_break_after_minutes=240 para o estrito do CTB §1-A.
    cct_max_driving_minutes: int = 270  # 4h30 conservador (CTB Art. 67-C §1-A: 4h)

    # min_break_minutes: pausa mínima obrigatória do motorista.
    #   CTB Art. 67-C §1-A: 30min de pausa a cada 4h de condução (passageiros).
    #   CLT Art. 235-C §2: intervalo de refeição mínimo de 1h (redutível a 30min via CCT).
    cct_min_break_minutes: int = 30  # 30min de pausa obrigatória (CTB Art. 67-C §1-A)

    # ── AI Copilot (OpenRouter) ───────────────────────────────────────────────
    openrouter_api_key: str = ""  # Chave de API. Vazia = recurso desativado silenciosamente.
    openrouter_model: str = ""  # Modelo preferencial (ex: deepseek/deepseek-v4-pro)

    # ── Celery / Redis (fila de tarefas assíncronas) ──────────────────────────
    redis_url: str = Field(default="redis://redis:6379/0", validation_alias="REDIS_URL")
    celery_task_soft_time_limit: int = 1200  # 20 min
    celery_task_time_limit: int = 1500  # 25 min

    # ── Roteamento OSRM ──────────────────────────────────────────────────────
    osrm_url: str = "http://localhost:5000"
    osrm_enabled: bool = True
    routing_cache_ttl: int = 86400  # 24 horas

    # ── Segurança Interna (Security Bridge) ──────────────────────────────────
    internal_security_key: str = Field(
        default="",
        validation_alias=AliasChoices("INTERNAL_OPTIMIZER_KEY", "internal_security_key"),
    )

    @field_validator("internal_security_key", mode="after")
    @classmethod
    def reject_known_default_key(cls, v: str) -> str:
        if not v or v == "internal-key-123456":
            raise ValueError("INTERNAL_OPTIMIZER_KEY must be set to a strong random value (not the default)")
        return v

    @field_validator("backend_secret", mode="after")
    @classmethod
    def reject_default_backend_secret(cls, v: str) -> str:
        if not v or v == "optimizer-internal-secret":
            raise ValueError("BACKEND_SECRET must be set to a strong random value (not the default)")
        return v

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)

        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
            return False
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
