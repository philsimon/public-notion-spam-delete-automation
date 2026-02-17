#!/usr/bin/env python3
"""Delete Notion database records based on property criteria.

This script queries a Notion database for records matching specific criteria
and archives them (moves to trash). It supports dry-run mode for safe testing
and implements rate limiting to respect Notion's API limits.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from typing import Dict, List, Optional

try:
    import httpx
except ImportError:
    print("Error: httpx package not installed.")
    print("Install with: pip install -r requirements.txt")
    sys.exit(1)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_api_key() -> str:
    """Get Notion API key from NOTION_API_KEY environment variable.

    Returns:
        str: The Notion API key

    Raises:
        SystemExit: If NOTION_API_KEY is not set
    """
    api_key = os.environ.get('NOTION_API_KEY')
    if not api_key:
        logger.error("NOTION_API_KEY environment variable not set")
        logger.error("Set it with: export NOTION_API_KEY='your_key_here'")
        sys.exit(1)

    # Strip whitespace and validate
    api_key = api_key.strip()

    # Validate API key format
    if not api_key.startswith('ntn_') and not api_key.startswith('secret_'):
        logger.error(f"Invalid API key format. Key should start with 'ntn_' or 'secret_'")
        logger.error(f"Key length: {len(api_key)} characters")
        sys.exit(1)

    # Check for invalid characters
    if '\n' in api_key or '\r' in api_key or '\t' in api_key:
        logger.error("API key contains invalid whitespace characters (newlines/tabs)")
        sys.exit(1)

    logger.info(f"API key loaded successfully ({len(api_key)} characters)")

    return api_key


def substitute_env_vars(text: str) -> str:
    """Substitute environment variables in text.

    Replaces ${VAR_NAME} patterns with values from environment variables.

    Args:
        text: Text containing ${VAR_NAME} patterns

    Returns:
        str: Text with environment variables substituted

    Raises:
        SystemExit: If a referenced environment variable is not set
    """
    def replace_var(match):
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            logger.error(f"Environment variable '{var_name}' is not set")
            logger.error(f"Required by configuration file")
            sys.exit(1)
        return value

    return re.sub(r'\$\{([^}]+)\}', replace_var, text)


def format_notion_id(notion_id: str) -> str:
    """Format Notion ID to UUID format with dashes.

    Notion IDs can be provided as 32-char hex strings or with dashes.
    The API requires UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

    Args:
        notion_id: Notion ID (with or without dashes)

    Returns:
        str: Formatted UUID with dashes
    """
    # Remove any existing dashes and spaces
    clean_id = notion_id.replace('-', '').replace(' ', '')

    # Validate it's 32 hex characters
    if len(clean_id) != 32:
        logger.warning(f"Invalid Notion ID length: {notion_id} (expected 32 chars, got {len(clean_id)})")
        return notion_id  # Return as-is if invalid

    # Format as UUID: 8-4-4-4-12
    return f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"


def load_deletion_rules(config_path: str) -> Dict:
    """Load deletion criteria from JSON configuration file.

    Args:
        config_path: Path to the JSON configuration file

    Returns:
        dict: Parsed configuration with database_id, filters, etc.

    Raises:
        SystemExit: If config file doesn't exist or is invalid JSON
    """
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)

    try:
        with open(config_path, 'r') as f:
            config_text = f.read()

        # Substitute environment variables in the config text
        config_text = substitute_env_vars(config_text)

        # Parse the JSON after substitution
        config = json.loads(config_text)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        sys.exit(1)

    # Validate structure
    if 'databases' not in config:
        logger.error("Configuration must contain 'databases' key")
        sys.exit(1)

    if not isinstance(config['databases'], list):
        logger.error("'databases' must be a list")
        sys.exit(1)

    for db_config in config['databases']:
        if 'database_id' not in db_config:
            logger.error("Each database configuration must have 'database_id'")
            sys.exit(1)
        if 'filters' not in db_config:
            logger.error("Each database configuration must have 'filters'")
            sys.exit(1)

    return config


def query_database(api_key: str, database_id: str, filters: Dict) -> List[str]:
    """Query Notion database for records matching deletion criteria.

    Args:
        api_key: Notion API key
        database_id: ID of the Notion database to query
        filters: Filter criteria in Notion's filter format

    Returns:
        list: List of page IDs that match the criteria
    """
    page_ids = []
    has_more = True
    start_cursor = None

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    }

    logger.info(f"Querying database {database_id} with filters: {json.dumps(filters, indent=2)}")

    try:
        while has_more:
            # Build request body
            body = {"filter": filters}
            if start_cursor:
                body["start_cursor"] = start_cursor

            # Query database using HTTP request
            response = httpx.post(
                f'https://api.notion.com/v1/databases/{database_id}/query',
                headers=headers,
                json=body,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

            # Extract page IDs from results
            for page in data.get('results', []):
                page_ids.append(page['id'])

            # Check if there are more results
            has_more = data.get('has_more', False)
            start_cursor = data.get('next_cursor')

            # Rate limiting between pages
            if has_more:
                time.sleep(0.35)

        logger.info(f"Found {len(page_ids)} records matching criteria")
        return page_ids

    except httpx.HTTPStatusError as e:
        logger.error(f"Error querying database: {e.response.text}")
        return []
    except Exception as e:
        logger.error(f"Error querying database: {e}")
        return []


def delete_page(api_key: str, page_id: str, dry_run: bool = False) -> bool:
    """Delete (archive) a single Notion page with retry logic.

    Args:
        api_key: Notion API key
        page_id: ID of the page to delete
        dry_run: If True, only log what would be deleted (don't actually delete)

    Returns:
        bool: True if successful, False otherwise
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would delete page: {page_id}")
        return True

    max_retries = 3
    retry_delay = 1  # Initial delay in seconds

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    }

    for attempt in range(max_retries):
        try:
            # Archive the page (moves to trash, recoverable for 30 days)
            response = httpx.patch(
                f'https://api.notion.com/v1/pages/{page_id}',
                headers=headers,
                json={"archived": True},
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"✓ Deleted page: {page_id}")

            # Rate limiting: 0.35 seconds = ~3 requests/second (Notion's limit)
            time.sleep(0.35)
            return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Exponential backoff for rate limits
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(f"Rate limited on page {page_id}, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                logger.error(f"Error deleting page {page_id}: {e.response.text}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error deleting page {page_id}: {e}")
            return False

    logger.error(f"Failed to delete page {page_id} after {max_retries} attempts")
    return False


def main():
    """Main execution flow."""
    parser = argparse.ArgumentParser(
        description='Delete Notion database records based on property criteria'
    )
    parser.add_argument(
        '--config',
        required=True,
        help='Path to JSON configuration file with deletion rules'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode: show what would be deleted without actually deleting'
    )

    args = parser.parse_args()

    # Check for DRY_RUN environment variable (set by GitHub Actions)
    env_dry_run = os.environ.get('DRY_RUN', '').lower() in ('true', '1', 'yes')
    dry_run = args.dry_run or env_dry_run

    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE: No actual deletions will occur")
        logger.info("=" * 60)

    # Get API key from environment
    api_key = get_api_key()

    # Load deletion rules from config file
    config = load_deletion_rules(args.config)

    # Statistics tracking
    total_queried = 0
    total_matched = 0
    total_deleted = 0
    total_failed = 0

    # Process each database in the configuration
    for db_config in config['databases']:
        database_id = format_notion_id(db_config['database_id'])
        database_name = db_config.get('name', database_id)
        filters = db_config['filters']

        # Override dry_run if specified in config
        db_dry_run = db_config.get('dry_run', dry_run)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing database: {database_name}")
        logger.info(f"Database ID: {database_id}")
        logger.info(f"{'=' * 60}")

        # Query for records matching deletion criteria
        page_ids = query_database(api_key, database_id, filters)
        total_queried += 1
        total_matched += len(page_ids)

        if not page_ids:
            logger.info("No records found matching deletion criteria")
            continue

        # Delete each matching record
        logger.info(f"\nDeleting {len(page_ids)} records...")
        for i, page_id in enumerate(page_ids, 1):
            logger.info(f"Processing record {i}/{len(page_ids)}")

            success = delete_page(api_key, page_id, dry_run=db_dry_run)
            if success:
                total_deleted += 1
            else:
                total_failed += 1

    # Print summary
    logger.info(f"\n{'=' * 60}")
    logger.info("CLEANUP SUMMARY")
    logger.info(f"{'=' * 60}")
    logger.info(f"Databases processed: {total_queried}")
    logger.info(f"Records matched: {total_matched}")
    logger.info(f"Records deleted: {total_deleted}")
    logger.info(f"Records failed: {total_failed}")

    if dry_run:
        logger.info(f"\nDRY RUN MODE: No actual deletions occurred")
    else:
        logger.info(f"\nDeleted records are in Notion trash (recoverable for 30 days)")

    # Exit with error code if any deletions failed
    if total_failed > 0:
        sys.exit(1)

    # Exit successfully if no failures occurred
    sys.exit(0)


if __name__ == '__main__':
    main()
