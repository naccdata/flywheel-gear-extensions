"""
Configuration management for the application.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional


@dataclass
class ApplicationConfig:
    """
    Configuration for the application.
    """
    input_path: Path
    output_path: Path
    qc_thresholds: Dict[str, float]
    scan_type_keywords: Dict[str, str]
    tag_name: str = "processed"
    log_level: str = "INFO"
    
    @classmethod
    def from_file(cls, config_path: Path) -> 'ApplicationConfig':
        """
        Load configuration from a file.
        
        Args:
            config_path: Path to the configuration file.
            
        Returns:
            ApplicationConfig instance.
            
        Raises:
            ValueError: If the configuration file is invalid.
        """
        pass

    @classmethod
    def from_env(cls) -> 'ApplicationConfig':
        """
        Load configuration from environment variables.
        
        Returns:
            ApplicationConfig instance.
            
        Raises:
            ValueError: If required environment variables are missing.
        """
        pass


def load_config(config_path: Optional[Path] = None) -> ApplicationConfig:
    """
    Load application configuration from file or environment.
    
    Args:
        config_path: Optional path to configuration file.
        
    Returns:
        ApplicationConfig instance.
    """
    if config_path and config_path.exists():
        return ApplicationConfig.from_file(config_path)
    return ApplicationConfig.from_env()
