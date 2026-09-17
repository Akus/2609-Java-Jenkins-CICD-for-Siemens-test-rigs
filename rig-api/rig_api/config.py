from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime knobs come from the environment (see docker-compose.yml / .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:////data/rigs.db"
    rigs_inventory: str = "rigs.yaml"
    poll_interval_s: float = 5.0
    poll_timeout_s: float = 2.0
    reservation_default_ttl_s: int = 1800
    watchdog_interval_s: float = 10.0
    quarantine_after_failures: int = 3
    log_level: str = "info"
    # Set to false in tests so the API can be exercised without background threads.
    background_tasks: bool = True


settings = Settings()
