from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "dev"
    port: int = 8000
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "smartbus"
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_tls: bool = False
    mqtt_username: str = "backend"
    mqtt_password: str = "change-me"
    mqtt_client_id: str = "backend-smartbus"
    default_bus_ids: str = "bus01"
    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_expire_minutes: int = Field(default=60, gt=0)
    cors_origins: str = "*"
    seed_admin_username: str = "admin"
    seed_admin_password: str = "change-me"
    seed_operator_username: str = "operator1"
    seed_operator_password: str = "change-me"
    seed_viewer_username: str = "viewer1"
    seed_viewer_password: str = "change-me"
    telemetry_ttl_days: int = Field(default=7, gt=0)
    node_offline_after_s: int = Field(default=10, gt=0)
    command_timeout_s: int = Field(default=10, gt=0)
    video_renew_s: float = Field(default=15, gt=0, lt=30)
    video_stop_grace_s: float = Field(default=5, gt=0)
    video_max_viewers: int = Field(default=5, ge=1)
    vision_stale_s: int = Field(default=10, gt=0)

    @model_validator(mode="after")
    def production_secrets(self) -> "Settings":
        if self.app_env == "production":
            secrets = (self.jwt_secret, self.mqtt_password, self.seed_admin_password,
                       self.seed_operator_password, self.seed_viewer_password)
            if any(not s or s.startswith("change-me") for s in secrets):
                raise ValueError("Phải cấu hình bí mật riêng khi triển khai")
            if len(self.jwt_secret) < 32 or not self.mqtt_tls:
                raise ValueError("Production cần JWT_SECRET >= 32 ký tự và MQTT_TLS=true")
        return self

    @property
    def bus_ids(self) -> list[str]:
        return [value.strip() for value in self.default_bus_ids.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
