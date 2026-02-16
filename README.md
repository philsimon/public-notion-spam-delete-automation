# Notion Database Cleanup Automation

Automatically archive spam records from Notion databases using GitHub Actions. This tool queries your Notion database for records matching specific criteria and moves them to trash on a scheduled basis.

## What This Does

This GitHub Action runs daily at midnight UTC (configurable). It:

1. Queries your Notion database for records matching specific criteria
2. Archives (moves to trash) all matching records
3. Logs detailed information about the cleanup operation
4. Respects Notion's API rate limits with built-in delays

### Safety Features

- **Dry-run mode** for testing before actual deletions
- **Moves to trash**, not permanent deletion (recoverable for 30 days)
- **Per-record error handling** (one failure doesn't stop the entire cleanup)
- **Rate limiting** (waits 0.35s between deletions)
- **Detailed logging** for full audit trail
- **Environment variable configuration** (no secrets in code)

## Security Notice

This repository uses environment variables for all sensitive configuration:
- API keys are stored in GitHub Secrets, never in code
- Database IDs are configured via environment variables
- Example configuration files contain only placeholders

## Setup Instructions

### 1. Get Your Notion API Key

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click "+ New integration"
3. Give it a name (e.g., "Database Cleanup")
4. Select the workspace where your database lives
5. Click "Submit"
6. Copy the "Internal Integration Token" (starts with `secret_`)

### 2. Share Database with Integration

1. Open your Notion database
2. Click the "..." menu in the top right
3. Scroll down and click "Add connections"
4. Select your integration name
5. Click "Confirm"

**Important:** The integration can only access databases you explicitly share with it.

### 3. Find Your Database ID

Your database ID is in the URL when viewing the database:

```
https://www.notion.so/your-workspace/DATABASE_ID?v=...
```

The `DATABASE_ID` is the 32-character string before the `?v=` parameter.

Example:
- URL: `https://www.notion.so/myworkspace/abc123def456...?v=xyz`
- Database ID: `abc123def456...` (32 characters)

You can also get the database ID by:
1. Right-click on the database
2. Select "Copy link"
3. Paste the link and extract the ID from the URL

### 4. Fork This Repository

1. Click the "Fork" button in the top right of this page
2. Select your GitHub account
3. Wait for the fork to complete

### 5. Configure GitHub Secrets

1. Go to your forked repository on GitHub
2. Click "Settings" → "Secrets and variables" → "Actions"
3. Click "New repository secret"
4. Add the following secrets:

**NOTION_API_KEY**
- Name: `NOTION_API_KEY`
- Value: Your Notion integration token (from step 1)

**NOTION_DATABASE_ID**
- Name: `NOTION_DATABASE_ID`
- Value: Your database ID (from step 3)

### 6. Customize Deletion Rules

Edit `config/deletion_rules.json` to match your specific filtering needs:

```json
{
  "databases": [
    {
      "database_id": "${NOTION_DATABASE_ID}",
      "name": "My Database",
      "filters": {
        "property": "Status",
        "select": {
          "equals": "Spam"
        }
      },
      "dry_run": false
    }
  ]
}
```

**Filter Examples:**

Delete records where a text property equals "Spam":
```json
"filters": {
  "property": "Organization",
  "rich_text": {
    "equals": "Spam"
  }
}
```

Delete records where a select property equals "Archived":
```json
"filters": {
  "property": "Status",
  "select": {
    "equals": "Archived"
  }
}
```

Delete records where a checkbox is checked:
```json
"filters": {
  "property": "Mark for Deletion",
  "checkbox": {
    "equals": true
  }
}
```

For more filter options, see [Notion's Filter Documentation](https://developers.notion.com/reference/post-database-query-filter).

### 7. Customize Schedule (Optional)

Edit `.github/workflows/notion-cleanup.yml` to change when the cleanup runs:

```yaml
on:
  schedule:
    # Daily at midnight UTC
    - cron: '0 0 * * *'
```

**Cron Examples:**
- `0 0 * * *` - Daily at midnight UTC
- `0 */6 * * *` - Every 6 hours
- `0 9 * * 1` - Every Monday at 9 AM UTC
- `0 0 * * 0` - Every Sunday at midnight UTC

Use [crontab.guru](https://crontab.guru/) to build custom schedules.

### 8. Test with Dry Run

Before enabling automatic deletions, test with dry-run mode:

1. Go to "Actions" tab in your repository
2. Click "Notion Database Cleanup" workflow
3. Click "Run workflow" button
4. Ensure "Dry run mode" is checked
5. Click "Run workflow"
6. Check the logs to see what would be deleted

### 9. Enable Automatic Cleanup

Once you've verified the dry run results:

1. Edit `config/deletion_rules.json`
2. Change `"dry_run": true` to `"dry_run": false`
3. Commit and push the changes
4. The workflow will now delete matching records on schedule

## Local Usage

You can also run the script locally for testing:

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/public-notion-spam-delete-automation.git
   cd public-notion-spam-delete-automation
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` and add your credentials:
   ```
   NOTION_API_KEY=secret_your_actual_key_here
   NOTION_DATABASE_ID=your_actual_database_id_here
   ```

### Run the Script

**Dry run (safe, shows what would be deleted):**
```bash
source .env
export NOTION_API_KEY NOTION_DATABASE_ID
python scripts/notion_cleanup.py --config config/deletion_rules.json --dry-run
```

**Actual deletion:**
```bash
source .env
export NOTION_API_KEY NOTION_DATABASE_ID
python scripts/notion_cleanup.py --config config/deletion_rules.json
```

## Troubleshooting

### "NOTION_API_KEY not set" error
- Ensure GitHub Secret is named exactly `NOTION_API_KEY`
- Check the secret is set in repository settings (not organization-level)
- Verify workflow YAML references the correct secret name

### "NOTION_DATABASE_ID not set" error
- Ensure GitHub Secret is named exactly `NOTION_DATABASE_ID`
- Verify you copied the full 32-character database ID
- Check that the database ID doesn't have extra spaces or characters

### "object not found" error
- Verify you've shared the database with your integration (step 2)
- Confirm the database ID is correct
- Check that the integration has the correct permissions

### No records found
- Verify your filter criteria in `deletion_rules.json`
- Check that records actually exist matching your criteria
- Test filters directly in Notion first to verify they work

### Rate limiting errors
- The script already includes delays (0.35s per request)
- If you still hit limits, you may be running other integrations simultaneously
- Wait a few minutes and try again

## Configuration Reference

### deletion_rules.json Structure

```json
{
  "databases": [
    {
      "database_id": "${NOTION_DATABASE_ID}",
      "name": "Human-readable name for logs",
      "filters": { /* Notion filter object */ },
      "dry_run": false
    }
  ]
}
```

**Fields:**
- `database_id`: Database ID (use `${NOTION_DATABASE_ID}` to reference the environment variable)
- `name`: Optional friendly name for the database (used in logs)
- `filters`: Notion API filter object ([documentation](https://developers.notion.com/reference/post-database-query-filter))
- `dry_run`: Set to `true` to simulate deletions without actually deleting

### Multiple Databases

You can clean up multiple databases in one run:

```json
{
  "databases": [
    {
      "database_id": "${NOTION_DATABASE_ID}",
      "name": "Contacts Database",
      "filters": {
        "property": "Type",
        "select": { "equals": "Spam" }
      },
      "dry_run": false
    },
    {
      "database_id": "${NOTION_DATABASE_ID_2}",
      "name": "Projects Database",
      "filters": {
        "property": "Status",
        "select": { "equals": "Archived" }
      },
      "dry_run": false
    }
  ]
}
```

Add additional database IDs as GitHub Secrets (e.g., `NOTION_DATABASE_ID_2`) and reference them in the config.

## How It Works

1. **Scheduled Trigger**: GitHub Actions runs the workflow on schedule or manual trigger
2. **Environment Setup**: Loads API key and database ID from GitHub Secrets
3. **Query Database**: Uses Notion API to query for matching records
4. **Archive Records**: Archives each matching record (moves to trash)
5. **Rate Limiting**: Waits 0.35s between requests to respect Notion's limits
6. **Error Handling**: Continues processing even if individual deletions fail
7. **Logging**: Uploads detailed logs as workflow artifacts

## License

MIT License - feel free to fork and customize for your needs.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review the workflow logs in the Actions tab
3. Open an issue with details about your problem

## Acknowledgments

- Built for automated Notion database maintenance
- Uses the official Notion API
- Designed with safety and recoverability in mind
