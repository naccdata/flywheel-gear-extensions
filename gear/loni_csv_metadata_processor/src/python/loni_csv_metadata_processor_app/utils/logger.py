"""
Logging utility for the application.
"""
import logging
from pathlib import Path
from typing import Optional


def setup_logger(name: str, log_level: int = logging.INFO, log_file: Optional[Path] = None) -> logging.Logger:
    """
    Set up a logger with the given name and log level.
    
    Args:
        name: Name of the logger.
        log_level: Logging level (default: INFO).
        log_file: Optional path to log file.
        
    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Add file handler if log_file is provided
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger
