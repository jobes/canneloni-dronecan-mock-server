#!/usr/bin/env python3

import argparse
import asyncio
import logging
from typing import cast

from app_runtime import run_server
from config_loader import load_config

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description='Cannelloni DroneCAN Mock Node')
    _ = parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to YAML or JSON config file (default: config.yaml)',
    )
    _ = parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Set the logging level (default: INFO)',
    )
    args = parser.parse_args()
    config_path = cast(str, args.config)
    log_level_name = cast(str, args.log_level)

    log_level = int(getattr(logging, log_level_name.upper(), logging.INFO))
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        logger.error('Error: Configuration file %s not found.', config_path)
        return
    except Exception as e:
        logger.error('Failed to load config %s: %s', config_path, e)
        return

    try:
        asyncio.run(run_server(config))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
