from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://grocery:grocery_dev_password@localhost:5432/grocery"
    cors_origins: str = "*"

    class Config:
        env_file = ".env"


settings = Settings()
