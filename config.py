"""
Configuration management module for Playwright RPA Agent.
Supports multiple LLM providers with persistent configuration.
"""
import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List
from pathlib import Path


# Default configurations for popular LLM providers
DEFAULT_PROVIDERS: Dict[str, Dict] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "description": "OpenAI GPT models"
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "description": "DeepSeek AI models"
    },
    "claude": {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-sonnet-20241022",
        "description": "Anthropic Claude models"
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
        "description": "Local Ollama models"
    },
    "custom": {
        "base_url": "",
        "default_model": "",
        "description": "Custom LLM provider"
    }
}


@dataclass
class LLMProviderConfig:
    """Configuration for a single LLM provider."""
    name: str
    api_key: str = ""
    base_url: str = ""
    model_name: str = ""
    description: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "LLMProviderConfig":
        return cls(**data)


@dataclass
class AppConfig:
    """Main application configuration."""
    # Currently active provider name
    active_provider: str = "openai"
    
    # All configured providers
    providers: Dict[str, LLMProviderConfig] = field(default_factory=dict)
    
    # Code execution settings
    execution_timeout: int = 300  # seconds
    max_fix_retries: int = 3
    
    # LLM request settings
    llm_max_retries: int = 3
    llm_retry_delay: float = 1.0  # seconds
    enable_streaming: bool = True
    
    # Security settings
    enable_code_validation: bool = True
    blocked_imports: List[str] = field(default_factory=lambda: [
        "subprocess", "os.system", "shutil.rmtree", "eval", "exec"
    ])
    
    # Recording settings
    recording_timeout: int = 600  # 10 minutes
    
    def __post_init__(self):
        """Initialize default providers."""
        # Always ensure all default providers exist
        for name, defaults in DEFAULT_PROVIDERS.items():
            if name not in self.providers:
                self.providers[name] = LLMProviderConfig(
                    name=name,
                    base_url=defaults["base_url"],
                    model_name=defaults["default_model"],
                    description=defaults["description"]
                )
    
    def get_active_provider(self) -> Optional[LLMProviderConfig]:
        """Get the currently active provider configuration."""
        return self.providers.get(self.active_provider)
    
    def set_provider(self, name: str, api_key: str = None, 
                     base_url: str = None, model_name: str = None) -> None:
        """Set or update a provider configuration."""
        if name not in self.providers:
            self.providers[name] = LLMProviderConfig(name=name)
        
        provider = self.providers[name]
        if api_key is not None:
            provider.api_key = api_key
        if base_url is not None:
            provider.base_url = base_url
        if model_name is not None:
            provider.model_name = model_name
    
    def switch_provider(self, name: str) -> bool:
        """Switch to a different provider."""
        if name in self.providers:
            self.active_provider = name
            return True
        return False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "active_provider": self.active_provider,
            "providers": {
                name: prov.to_dict() 
                for name, prov in self.providers.items()
            },
            "execution_timeout": self.execution_timeout,
            "max_fix_retries": self.max_fix_retries,
            "llm_max_retries": self.llm_max_retries,
            "llm_retry_delay": self.llm_retry_delay,
            "enable_streaming": self.enable_streaming,
            "enable_code_validation": self.enable_code_validation,
            "blocked_imports": self.blocked_imports,
            "recording_timeout": self.recording_timeout
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AppConfig":
        """Create config from dictionary."""
        providers = {}
        for name, prov_data in data.get("providers", {}).items():
            providers[name] = LLMProviderConfig.from_dict(prov_data)
        
        return cls(
            active_provider=data.get("active_provider", "openai"),
            providers=providers,
            execution_timeout=data.get("execution_timeout", 300),
            max_fix_retries=data.get("max_fix_retries", 3),
            llm_max_retries=data.get("llm_max_retries", 3),
            llm_retry_delay=data.get("llm_retry_delay", 1.0),
            enable_streaming=data.get("enable_streaming", True),
            enable_code_validation=data.get("enable_code_validation", True),
            blocked_imports=data.get("blocked_imports", [
                "subprocess", "os.system", "shutil.rmtree", "eval", "exec"
            ]),
            recording_timeout=data.get("recording_timeout", 600)
        )


class ConfigManager:
    """Manages configuration persistence and loading."""
    
    DEFAULT_CONFIG_PATH = Path.home() / ".playwright_rpa_agent" / "config.json"
    
    def __init__(self, config_path: Path = None):
        self.config_path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        self._config: Optional[AppConfig] = None
    
    def load(self) -> AppConfig:
        """Load configuration from file or create default."""
        if self._config is not None:
            return self._config
        
        # Try loading from environment variables first
        env_config = self._load_from_env()
        
        # Then try loading from file
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._config = AppConfig.from_dict(data)
                
                # Merge environment variables (they take priority)
                self._merge_env_config(env_config)
                return self._config
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Failed to load config from {self.config_path}: {e}")
        
        # Create default config
        self._config = AppConfig()
        self._merge_env_config(env_config)
        return self._config
    
    def _load_from_env(self) -> Dict:
        """Load configuration from environment variables."""
        env_config = {}
        
        # Support common environment variable patterns
        env_mappings = {
            "OPENAI_API_KEY": ("openai", "api_key"),
            "OPENAI_BASE_URL": ("openai", "base_url"),
            "DEEPSEEK_API_KEY": ("deepseek", "api_key"),
            "DEEPSEEK_BASE_URL": ("deepseek", "base_url"),
            "ANTHROPIC_API_KEY": ("claude", "api_key"),
            "CLAUDE_API_KEY": ("claude", "api_key"),
            "LLM_API_KEY": ("active", "api_key"),  # Generic fallback
            "LLM_BASE_URL": ("active", "base_url"),
            "LLM_MODEL": ("active", "model_name"),
        }
        
        for env_var, (provider, field) in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                if provider not in env_config:
                    env_config[provider] = {}
                env_config[provider][field] = value
        
        return env_config
    
    def _merge_env_config(self, env_config: Dict) -> None:
        """Merge environment config into loaded config."""
        if not self._config:
            return
        
        for provider_name, settings in env_config.items():
            if provider_name == "active":
                # Apply to currently active provider
                active = self._config.get_active_provider()
                if active:
                    for field, value in settings.items():
                        setattr(active, field, value)
            elif provider_name in self._config.providers:
                provider = self._config.providers[provider_name]
                for field, value in settings.items():
                    setattr(provider, field, value)
    
    def save(self, config: AppConfig = None) -> bool:
        """Save configuration to file."""
        if config:
            self._config = config
        
        if not self._config:
            return False
        
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"Error saving config: {e}")
            return False
    
    def reset(self) -> AppConfig:
        """Reset to default configuration."""
        self._config = AppConfig()
        return self._config
    
    @property
    def config(self) -> AppConfig:
        """Get current config, loading if necessary."""
        if self._config is None:
            self.load()
        return self._config


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get or create the global config manager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> AppConfig:
    """Convenience function to get current config."""
    return get_config_manager().config
