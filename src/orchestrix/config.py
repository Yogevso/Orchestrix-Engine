from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://orchestrix:orchestrix@localhost:5432/orchestrix"
    database_url_sync: str = "postgresql://orchestrix:orchestrix@localhost:5432/orchestrix"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Worker
    worker_poll_interval: float = 1.0
    lease_duration_seconds: int = 60
    heartbeat_interval_seconds: int = 10
    heartbeat_timeout_seconds: int = 30

    # Retry
    max_default_attempts: int = 3
    retry_base_delay_seconds: float = 2.0
    retry_max_delay_seconds: float = 300.0

    # Concurrency
    default_queue_max_concurrency: int = 0  # 0 = unlimited

    # Scheduler
    scheduler_check_interval: float = 5.0

    # Metrics
    metrics_enabled: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Auth / JWT
    auth_enabled: bool = False
    jwt_secret_key: str = "orchestrix-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # OpenTelemetry
    otel_enabled: bool = False
    otel_exporter_endpoint: str = "http://localhost:4317"

    model_config = {"env_prefix": "ORCHESTRIX_"}


settings = Settings()
