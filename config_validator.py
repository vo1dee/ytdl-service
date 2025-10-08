"""
Configuration validation module for YouTube Download Service.
Validates environment variables and configuration on application startup.
"""

import os
import sys
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass

class ConfigValidator:
    """Validates application configuration and environment variables."""
    
    # Required environment variables (must be set)
    REQUIRED_VARS = []
    
    # Optional environment variables with their default values and validation
    OPTIONAL_VARS = {
        'YTDL_SERVICE_URL': {
            'default': 'http://localhost:8000',
            'description': 'Service URL for internal communication',
            'validator': lambda x: x.startswith(('http://', 'https://'))
        },
        'YTDL_SERVICE_API_KEY': {
            'default': None,
            'description': 'API key for service authentication (auto-generated if not provided)',
            'validator': lambda x: len(x) >= 8 if x else True
        },
        'PORT': {
            'default': '8000',
            'description': 'Port for the FastAPI service',
            'validator': lambda x: x.isdigit() and 1 <= int(x) <= 65535
        },
        'YTDL_MAX_RETRIES': {
            'default': '3',
            'description': 'Number of retry attempts for failed downloads',
            'validator': lambda x: x.isdigit() and 1 <= int(x) <= 10
        },
        'YTDL_RETRY_DELAY': {
            'default': '1',
            'description': 'Delay between retry attempts (in seconds)',
            'validator': lambda x: x.isdigit() and 0 <= int(x) <= 60
        },
        'DOWNLOADS_DIR': {
            'default': '/opt/ytdl_service/downloads',
            'description': 'Downloads directory path',
            'validator': lambda x: (os.path.isabs(x) or x.startswith('/')) if x else True
        },
        'LOGS_DIR': {
            'default': '/var/log',
            'description': 'Logs directory path',
            'validator': lambda x: (os.path.isabs(x) or x.startswith('/')) if x else True
        },
        'API_KEY_FILE': {
            'default': '/opt/ytdl_service/config/api_key.txt',
            'description': 'API key file path',
            'validator': lambda x: (os.path.isabs(x) or x.startswith('/')) if x else True
        },
        'YTDLP_UPDATE_INTERVAL': {
            'default': '86400',
            'description': 'yt-dlp update check interval (in seconds)',
            'validator': lambda x: x.isdigit() and int(x) >= 3600  # At least 1 hour
        },
        'CLEANUP_INTERVAL': {
            'default': '3600',
            'description': 'File cleanup interval (in seconds)',
            'validator': lambda x: x.isdigit() and int(x) >= 300  # At least 5 minutes
        },
        'FILE_MAX_AGE': {
            'default': '86400',
            'description': 'Maximum age for downloaded files before cleanup (in seconds)',
            'validator': lambda x: x.isdigit() and int(x) >= 3600  # At least 1 hour
        },
        'TELEGRAM_BOT_TOKEN': {
            'default': None,
            'description': 'Telegram bot token (optional)',
            'validator': lambda x: len(x.split(':')) == 2 if x else True
        },
        'TELEGRAM_ERROR_CHAT_ID': {
            'default': None,
            'description': 'Chat ID for error reporting (optional)',
            'validator': lambda x: x.lstrip('-').isdigit() if x else True
        },
        'DEBUG': {
            'default': 'false',
            'description': 'Debug mode',
            'validator': lambda x: x.lower() in ('true', 'false', '1', '0', 'yes', 'no')
        },
        'LOG_LEVEL': {
            'default': 'INFO',
            'description': 'Log level',
            'validator': lambda x: x.upper() in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        }
    }
    
    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """
        Validate all configuration and return validated config dictionary.
        
        Returns:
            Dict containing validated configuration values
            
        Raises:
            ConfigValidationError: If validation fails
        """
        config = {}
        errors = []
        warnings = []
        
        # Check required variables
        for var_name in cls.REQUIRED_VARS:
            value = os.getenv(var_name)
            if not value:
                errors.append(f"Required environment variable '{var_name}' is not set")
            else:
                config[var_name] = value
        
        # Check optional variables
        for var_name, var_config in cls.OPTIONAL_VARS.items():
            value = os.getenv(var_name, var_config['default'])
            
            if value is not None:
                # Validate the value
                try:
                    if not var_config['validator'](value):
                        errors.append(
                            f"Invalid value for '{var_name}': '{value}'. "
                            f"{var_config['description']}"
                        )
                    else:
                        config[var_name] = value
                except Exception as e:
                    errors.append(
                        f"Validation error for '{var_name}': {str(e)}"
                    )
            else:
                config[var_name] = None
        
        # Directory validation
        cls._validate_directories(config, errors, warnings)
        
        # Log configuration summary
        cls._log_config_summary(config, warnings)
        
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
            logger.error(error_msg)
            raise ConfigValidationError(error_msg)
        
        return config
    
    @classmethod
    def _validate_directories(cls, config: Dict[str, Any], errors: List[str], warnings: List[str]):
        """Validate directory paths and permissions."""
        directories_to_check = [
            ('DOWNLOADS_DIR', True),  # (env_var_name, should_be_writable)
            ('LOGS_DIR', True),
        ]
        
        for dir_var, should_be_writable in directories_to_check:
            dir_path = config.get(dir_var)
            if not dir_path:
                continue
                
            try:
                # Try to create directory if it doesn't exist
                try:
                    Path(dir_path).mkdir(parents=True, exist_ok=True)
                except PermissionError:
                    # If we can't create it due to permissions, just warn
                    warnings.append(f"Cannot create directory '{dir_path}' ({dir_var}) due to permissions. Ensure it exists at runtime.")
                    continue
                except Exception as e:
                    warnings.append(f"Cannot create directory '{dir_path}' ({dir_var}): {str(e)}. Ensure it exists at runtime.")
                    continue
                
                # Check if directory is accessible (only if it exists)
                if os.path.exists(dir_path):
                    if not os.path.isdir(dir_path):
                        errors.append(f"Path '{dir_path}' ({dir_var}) exists but is not a directory")
                    elif should_be_writable and not os.access(dir_path, os.W_OK):
                        warnings.append(f"Directory '{dir_path}' ({dir_var}) is not writable")
                    elif not os.access(dir_path, os.R_OK):
                        warnings.append(f"Directory '{dir_path}' ({dir_var}) is not readable")
                    
            except Exception as e:
                warnings.append(f"Error validating directory '{dir_path}' ({dir_var}): {str(e)}")
        
        # Validate API key file directory
        api_key_file = config.get('API_KEY_FILE')
        if api_key_file:
            api_key_dir = os.path.dirname(api_key_file)
            try:
                try:
                    Path(api_key_dir).mkdir(parents=True, exist_ok=True)
                except PermissionError:
                    warnings.append(f"Cannot create API key directory '{api_key_dir}' due to permissions. API key auto-generation may fail.")
                    return
                    
                if os.path.exists(api_key_dir) and not os.access(api_key_dir, os.W_OK):
                    warnings.append(f"API key directory '{api_key_dir}' is not writable. API key auto-generation may fail.")
            except Exception as e:
                warnings.append(f"Could not validate API key directory '{api_key_dir}': {str(e)}")
    
    @classmethod
    def _log_config_summary(cls, config: Dict[str, Any], warnings: List[str]):
        """Log configuration summary."""
        logger.info("=== Configuration Summary ===")
        
        # Log key configuration values (excluding sensitive data)
        sensitive_vars = {'YTDL_SERVICE_API_KEY', 'TELEGRAM_BOT_TOKEN'}
        
        for var_name, value in config.items():
            if var_name in sensitive_vars:
                if value:
                    logger.info(f"  {var_name}: [SET]")
                else:
                    logger.info(f"  {var_name}: [NOT SET]")
            else:
                logger.info(f"  {var_name}: {value}")
        
        # Log warnings
        if warnings:
            logger.warning("Configuration warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
        
        logger.info("=== End Configuration Summary ===")
    
    @classmethod
    def get_config_documentation(cls) -> str:
        """Generate documentation for all configuration variables."""
        doc_lines = ["# Environment Variables Documentation", ""]
        
        if cls.REQUIRED_VARS:
            doc_lines.extend(["## Required Variables", ""])
            for var_name in cls.REQUIRED_VARS:
                doc_lines.append(f"- **{var_name}**: (Required)")
            doc_lines.append("")
        
        doc_lines.extend(["## Optional Variables", ""])
        for var_name, var_config in cls.OPTIONAL_VARS.items():
            default_val = var_config['default'] or 'None'
            doc_lines.append(f"- **{var_name}**: {var_config['description']}")
            doc_lines.append(f"  - Default: `{default_val}`")
            doc_lines.append("")
        
        return "\n".join(doc_lines)

def validate_startup_config() -> Dict[str, Any]:
    """
    Validate configuration on application startup.
    
    Returns:
        Dict containing validated configuration
        
    Raises:
        SystemExit: If validation fails
    """
    try:
        return ConfigValidator.validate_config()
    except ConfigValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        logger.error("Please check your environment variables and try again.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during configuration validation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Generate documentation when run directly
    print(ConfigValidator.get_config_documentation())