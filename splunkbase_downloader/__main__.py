#!/usr/bin/python3
# -*- coding: utf-8 -*-

import logging
import sys

try:
    from .app_downloader import main as downloader_main
except ImportError:
    from app_downloader import main as downloader_main

def main():
    """
    Main entry point to the application.
    Configures and starts downloading Splunk configurations.
    """
    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting Splunk configuration download")
        downloader_main()
        logger.info("Download completed successfully")
        return 0
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
