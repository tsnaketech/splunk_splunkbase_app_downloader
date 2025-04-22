# -*- coding: utf-8 -*-

import argparse
import configparser
import os
import yaml
from dotenv import load_dotenv
from typing import Any, Dict, Optional

class ConfigurationManagerError(Exception):
    pass

class ConfigurationManager:
    """A configuration manager that handles multiple configuration sources."""

    def __init__(self, description: str = "Application configuration", **kwargs):
        """
        Initialize the configuration manager.

        Args:
            description: Description for the argument parser
        """
        self.parser = argparse.ArgumentParser(description=description)
        self.add_argument("--config", "-c", type=str, help="Path to the configuration file", required=False)
        self.config_data: Dict[str, Any] = {}
        self.yaml_data: Dict[str, Any] = {}
        self.ini_data: Dict[str, Any] = {}
        self.kwargs = kwargs
        self._load_env()

    def _load_env(self) -> None:
        """Load environment variables from .env file and store them."""
        load_dotenv()

    def _load_ini_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from an INI file.

        Args:
            config_path: Path to the INI configuration file

        Returns:
            Dictionary containing the configuration
        """
        config = configparser.ConfigParser()
        config.read(config_path)
        return {section: dict(config[section]) for section in config.sections()}

    def _load_yaml_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from a YAML file.

        Args:
            config_path: Path to the YAML configuration file

        Returns:
            Dictionary containing the configuration
        """
        with open(config_path, 'r') as yaml_file:
            return yaml.safe_load(yaml_file)

    def add_argument(self, *args, **kwargs) -> None:
        """
        Add an argument to the argument parser.

        Args:
            *args: Positional arguments for ArgumentParser.add_argument
            **kwargs: Keyword arguments for ArgumentParser.add_argument
        """
        # Add the argument to the parser
        self.parser.add_argument(*args, **kwargs)

    def load_config_file(self, config_path: Optional[str]) -> None:
        """
        Load configuration from a file (INI or YAML).

        Args:
            config_path: Path to the configuration file
        """
        if not config_path:
            return

        try:
            if config_path.endswith(('.conf', '.ini')):
                self.ini_data = self._load_ini_config(config_path)
            elif config_path.endswith(('.yaml', '.yml')):
                self.yaml_data  = self._load_yaml_config(config_path)
        except FileNotFoundError:
            print(f"Configuration file {config_path} not found. Continuing without it.")

    def set_config(self, key: str, section: Optional[str] = None, env_key: Optional[str] = None, default: Any = None) -> Any:
        """
        Set the configuration value for a given key, checking various sources in a specific order.

        Args:
            key (str): The configuration key to set.
            section (Optional[str]): The section in the configuration files to look for the key. Defaults to None.
            env_key (Optional[str]): The environment variable key to look for. Defaults to None.
            default (Any): The default value to return if the key is not found in any source. Defaults to None.

        Returns:
            Any: The value of the configuration key from the first source where it is found, or the default value if not found.
        """
        args = vars(self.parser.parse_args())

        # Convert key for arg format (replace dots with hyphens)
        arg_key = key.replace('.', '-')

        arg_def = self.parser._option_string_actions.get(f'--{arg_key}')
        valid_choices = getattr(arg_def, 'choices', None) if arg_def else None

        value =  (
            # Check CLI args
            args.get(arg_key) or

            # Check YAML with section
            (self.yaml_data.get(section, {}).get(key) if section else self.yaml_data.get(key)) or

            # Check INI with section
            (self.ini_data.get(section, {}).get(key) if section else self.ini_data.get(key)) or

            # Check environment variables
            os.getenv(env_key or key.upper()) or

            # Check kwargs with section
            (self.kwargs.get(section, {}).get(key) if section else self.kwargs.get(key)) or

            # Return default value
            default
        )

        # Validate against choices if defined
        if valid_choices is not None:
            if value not in valid_choices:
                raise ConfigurationManagerError(f"Invalid value '{value}' for {key}. Must be one of: {valid_choices}")

        if section:
            self.config_data.setdefault(section, {})
            self.config_data[section][key] = value
        else:
            self.config_data[key] = value
        return value

    def set_config_group(self, section: str = "", keys: list = [], env_prefix: str = "") -> Dict[str, Any]:
        """
        Sets a configuration group by applying the set_config method to each key in the provided list.

        Args:
            section (str): The configuration section to use.
            keys (list): A list of keys for which the configuration should be set.
            env_prefix (str, optional): An optional environment variable prefix to use for the keys. Defaults to "".

        Returns:
            Dict[str, Any]: A dictionary where each key is mapped to its corresponding configuration value.
        """

        return {
            key: self.set_config(
                key=key,
                section=section,
                env_key=f"{env_prefix}_{key.upper()}" if env_prefix else None
            )
            for key in keys
        }

    def get_config_value(self, key):
        """
        Retrieve the value of a specified configuration key.

        Args:
            key (str): The key for which the configuration value is to be retrieved.

        Returns:
            The value associated with the specified key, or None if the key is not found.
        """

        return self.config_data.get(key)