"""
Logging configuration for Playwright RPA Agent.
Provides structured logging with file and console output.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class RPALogger:
    """Centralized logging for the RPA Agent."""
    
    DEFAULT_LOG_DIR = Path.home() / ".playwright_rpa_agent" / "logs"
    DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    
    _instance: Optional["RPALogger"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, log_dir: Path = None, level: int = logging.INFO):
        if self._initialized:
            return
        
        self.log_dir = log_dir or self.DEFAULT_LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create main logger
        self.logger = logging.getLogger("rpa_agent")
        self.logger.setLevel(level)
        self.logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(self.DEFAULT_FORMAT))
        self.logger.addHandler(console_handler)
        
        # File handler (daily rotation)
        log_file = self.log_dir / f"rpa_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(self.DEFAULT_FORMAT))
        self.logger.addHandler(file_handler)
        
        self._initialized = True
    
    def get_logger(self, name: str = None) -> logging.Logger:
        """Get a child logger with optional name."""
        if name:
            return self.logger.getChild(name)
        return self.logger


def get_logger(name: str = None) -> logging.Logger:
    """Convenience function to get a logger."""
    rpa_logger = RPALogger()
    return rpa_logger.get_logger(name)
