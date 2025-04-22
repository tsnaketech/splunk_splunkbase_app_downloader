#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import json
import logging
import os
import sys
from io import open
from typing import Dict, List, Optional, Tuple

import requests

try:
    from .config_manager import ConfigurationManager
except ImportError:
    from config_manager import ConfigurationManager


class SplunkbaseDownloader:
    """Handles authentication and downloading of Splunk apps from Splunkbase."""

    BASE_URL = "https://splunkbase.splunk.com"
    DOWNLOAD_API = "https://api.splunkbase.splunk.com/api/v2/apps/{app_id}/releases/{version}/download/?origin=sb&lead=false"
    VERSION_API = f"{BASE_URL}/api/v1/app/{{uid}}/release/"
    LOGIN_API = f"{BASE_URL}/api/account:login/"

    def __init__(self, **kwargs):
        """
        Initialize the downloader with configuration files.

        Args:
            config_file: Path to the login credentials file
            apps_file: Path to the apps configuration file
        """

        self._config = ConfigurationManager(**kwargs)
        self._get_args()
        self.args_splunkbase = self._config.config_data.get("splunkbase", {})
        self.args_apps = self._config.config_data.get("apps", {})
        self.apps_file = self.args_apps.get("file", None)
        self.output = self.args_apps.get("output", "./")
        self.cookies = None
        self.logger = self._setup_logger()

    def _get_args(self) -> dict:
        self._config.add_argument("--username", "-u", type=str, help="Splunkbase username", required=False)
        self._config.add_argument("--password", "-p", type=str, help="Splunkbase password", required=False)
        self._config.add_argument("--apps_file", "-a", type=str, help="Path to the apps list file", required=False)
        self._config.add_argument("--output", "-o", type=str, help="Output directory", required=False)
        args = self._config.parser.parse_args()

        self._config.load_config_file(args.config)
        self._config.set_config_group(section="splunkbase", keys=["username", "password"], env_prefix="SPLUNK_ASD")
        self._config.set_config_group(section="apps", keys=["file", "output"], env_prefix="SPLUNK_ASD")

    @staticmethod
    def _setup_logger() -> logging.Logger:
        """Configure and return a logger for the application."""
        logger = logging.getLogger("SplunkbaseDownloader")
        logger.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # Format
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(console_handler)

        return logger

    def authenticate(self) -> None:
        """
        Authenticate with Splunkbase using credentials from the config file.

        Raises:
            FileNotFoundError: If login config file doesn't exist
            Exception: If authentication fails
        """
        try:
            payload = {
                'username': self.args_splunkbase.get('username', None),
                'password': self.args_splunkbase.get('password', None)
            }

            self.logger.info("Authenticating with Splunkbase...")
            response = requests.post(self.LOGIN_API, data=payload)

            if response.status_code == 200:
                self.cookies = response.cookies.get_dict()
                self.logger.info("Authentication successful")
            else:
                raise Exception(f"Authentication failed with status code: {response.status_code}")
        except Exception as e:
            self.logger.error(f"Authentication error: {str(e)}")
            raise

    def get_latest_version(self, uid: str) -> Optional[str]:
        """
        Retrieve the latest version of an app from Splunkbase.

        Args:
            uid: The app's unique identifier

        Returns:
            The latest version string or None if retrieval fails
        """
        if not self.cookies:
            self.logger.error("Not authenticated. Call authenticate() first.")
            return None

        url = self.VERSION_API.format(uid=uid)

        try:
            response = requests.get(url, cookies=self.cookies)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return data[0]['name']  # Assuming the first version is the latest
                else:
                    self.logger.warning(f"No versions found for app {uid}")
                    return None
            else:
                self.logger.error(f"Error retrieving app version for {uid}: Status code {response.status_code}")
                return None

        except Exception as e:
            self.logger.error(f"Error getting latest version for {uid}: {str(e)}")
            return None

    def download_app(self, app_name: str, app_id: str, app_version: str) -> Optional[str]:
        """
        Download a specific version of an app if it doesn't already exist.

        Args:
            app_id: The app's unique identifier
            app_version: The version to download

        Returns:
            The update timestamp if successful, None otherwise
        """
        if not self.cookies:
            self.logger.error("Not authenticated. Call authenticate() first.")
            return None

        file_name = f"{app_name}_{app_id}_{app_version}.tgz"

        # Ensure the output directory exists
        if not os.path.exists(self.output):
            os.makedirs(self.output)
        path = os.path.join(self.output, file_name)

        # Check if file already exists
        if os.path.exists(path):
            self.logger.info(f"Skipping download of {file_name} (already exists)")
            return None

        download_url = self.DOWNLOAD_API.format(app_id=app_id, version=app_version)

        try:
            self.logger.info(f"Downloading {path}...")
            response = requests.get(download_url, cookies=self.cookies)

            if response.status_code == 200:
                with open(path, 'wb') as file:
                    file.write(response.content)

                # Get update timestamp or use current time
                updated_time = response.headers.get("Last-Modified")
                if not updated_time:
                    updated_time = datetime.datetime.utcnow().isoformat() + "Z"

                self.logger.info(f"Successfully downloaded {path}")
                return updated_time
            else:
                self.logger.error(f"Failed to download {path}. Status code: {response.status_code}")
                return None

        except Exception as e:
            self.logger.error(f"Error downloading {app_id} v{app_version}: {str(e)}")
            return None

    def update_apps_file(self, uid: str, new_version: str, updated_time: str) -> bool:
        """
        Update the apps configuration file with new version information.

        Args:
            uid: The app's unique identifier
            new_version: The new app version
            updated_time: The update timestamp

        Returns:
            True if update was successful, False otherwise
        """
        try:
            # Read current data
            with open(self.apps_file, 'r', encoding='utf-8') as file:
                apps_data = json.load(file)

            # Find and update the app entry
            app_updated = False
            for app in apps_data:
                if app['uid'] == uid:
                    app['version'] = new_version
                    app['updated_time'] = updated_time
                    app_updated = True
                    break

            if not app_updated:
                self.logger.warning("App %s not found in %s", uid, self.apps_file)
                return False

            # Write updated data back to file
            with open(self.apps_file, 'w', encoding='utf-8') as file:
                json.dump(apps_data, file, indent=4)

            self.logger.info("Updated %s with new version for %s: %s", self.apps_file, uid, new_version)
            return True

        except Exception as e:
            self.logger.error("Error updating apps file: %s", str(e))
            return False

    def check_and_update_apps(self) -> Tuple[List[str], List[str]]:
        """
        Check all apps in the configuration for updates and download new versions.

        Returns:
            Tuple of (downloaded_apps, skipped_apps)
        """
        if not self.cookies:
            self.logger.error("Not authenticated. Call authenticate() first.")
            return [], []

        downloaded_apps = []
        skipped_apps = []

        try:
            # Read apps configuration
            with open(self.apps_file, 'r') as file:
                apps_data = json.load(file)

            self.logger.info(f"Checking updates for {len(apps_data)} apps...")

            # Process each app
            for app in apps_data:
                name = app.get('name')
                uid = app.get('uid')
                current_version = app.get('version')

                # Get latest version from Splunkbase
                latest_version = self.get_latest_version(uid)

                if not latest_version:
                    self.logger.warning(f"Could not retrieve latest version for {uid}")
                    skipped_apps.append(f"{name}_{uid}_{current_version}")
                    continue

                # Check if update is needed
                if latest_version != current_version:
                    self.logger.info(f"Update available for {uid}: {current_version} → {latest_version}")

                    # Download new version
                    updated_time = self.download_app(name, uid, latest_version)

                    if updated_time:
                        # Update app info in configuration file
                        self.update_apps_file(uid, latest_version, updated_time)
                        downloaded_apps.append(f"{name}_{uid}_{latest_version}")
                    else:
                        skipped_apps.append(f"{name}_{uid}_{latest_version}")
                else:
                    self.logger.info(f"App {uid} is up to date (version {current_version})")
                    skipped_apps.append(f"{name}_{uid}_{current_version}")

            return downloaded_apps, skipped_apps

        except FileNotFoundError:
            self.logger.error(f"Apps file '{self.apps_file}' not found")
            return [], []
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in '{self.apps_file}'")
            return [], []
        except Exception as e:
            self.logger.error(f"Error checking for updates: {str(e)}")
            return [], []


def main():
    """Main entry point for the script."""
    try:
        # Create downloader instance
        downloader = SplunkbaseDownloader()

        # Authenticate
        downloader.authenticate()

        # Check for updates and download new versions
        downloaded, skipped = downloader.check_and_update_apps()

        # Output results
        if downloaded:
            print("\nDownloaded apps:")
            for app in downloaded:
                print(f"  - {app}")
        else:
            print("\nNo new apps downloaded")

        if skipped:
            print("\nSkipped apps:")
            for app in skipped:
                print(f"  - {app}")

        print("\nProcess completed successfully")

    except Exception as e:
        print(f"\nAn error occurred during execution: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()