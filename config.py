from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings."""
    
    # Bot settings
    bot_token: str
    
    # Database settings
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str
    
    # Admin settings
    admin_ids: str = ""
    
    # Financial defaults
    default_cny_rate: float = 12.5
    default_delivery_cost_per_kg: float = 350.0
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    @property
    def database_url(self) -> str:
        """Generate database URL for SQLAlchemy."""
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def admin_list(self) -> List[int]:
        """Parse admin IDs from comma-separated string."""
        if not self.admin_ids:
            return []
        return [int(admin_id.strip()) for admin_id in self.admin_ids.split(",") if admin_id.strip()]


# Create global settings instance
settings = Settings()

