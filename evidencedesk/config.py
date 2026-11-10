from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


class SetupError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    nebius_key: str = field(repr=False)
    tavily_key: str = field(repr=False)
    model: str = "Qwen/Qwen3-235B-A22B-Instruct-2507"
    max_sources: int = 6
    max_searches: int = 3

    @classmethod
    def load(cls, *, require_keys=True):
        load_dotenv(ROOT / ".env", override=False)
        settings = cls(os.getenv("NEBIUS_API_KEY", "").strip(),
                       os.getenv("TAVILY_API_KEY", "").strip(),
                       os.getenv("NEBIUS_MODEL", cls.model).strip())
        missing = [name for name, val in [("NEBIUS_API_KEY", settings.nebius_key),
                                           ("TAVILY_API_KEY", settings.tavily_key)] if not val]
        if require_keys and missing:
            raise SetupError("Add " + " and ".join(missing) + " to the local .env file, then restart.")
        return settings
