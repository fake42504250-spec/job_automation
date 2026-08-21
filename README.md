# Job Automation

A local-first Python system that discovers relevant internships from your Gmail job-alert label and optional RSS feeds, scores them against your profile, finds evidence-backed corporate contacts, generates personalized recruiter emails, sends a capped sequence, detects replies, schedules up to two follow-ups, and displays everything at `http://127.0.0.1:8000`.

The system intentionally does **not** automate LinkedIn. It does not scrape LinkedIn profiles, send connection requests, or send LinkedIn messages.

## What is automated

- Read native job-alert emails from a Gmail label
- Read optional RSS/Atom job feeds
- Deduplicate and score Backend/SDE, Full Stack, GenAI and ML internships
- Reject senior roles automatically
- Extract corporate emails stated in job descriptions or public company pages
- Optionally discover role-relevant corporate contacts through Hunter's API
- Generate a job-specific recruiter/referral message from your profile
- Enforce a daily send limit and maximum contacts per company
- Detect Gmail replies and stop follow-ups
- Schedule follow-ups after configurable delays
- Run once, run as a background scheduler, or use the local dashboard

## Important limitations

No responsible tool can guarantee that an internship converts to an FTE role or that the converted compensation will exceed ₹15 LPA. Use job descriptions, recruiter confirmation and public compensation evidence to validate that separately.

Contact discovery works only when an address is publicly stated or an optional contact provider returns one. The system never guesses personal addresses and rejects Gmail/Yahoo/Outlook recipients.

## Windows setup

After cloning the repository, the shortest setup is:

1. Right-click `setup_windows.ps1` and choose **Run with PowerShell**.
2. Complete the one-time Gmail connection described below.
3. Double-click `start_windows.bat` whenever you want the automation running.

The equivalent PowerShell commands are:

```powershell
git clone https://github.com/fake42504250-spec/job_automation.git
cd job_automation

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"

job-automation init
```

`init` creates two private local files that Git will ignore:

- `.env`
- `config/profile.yaml`

Edit `config/profile.yaml` with your details, project proof, resume link and GitHub link.

## One-time Gmail connection

Google requires the account owner to approve access once. This cannot safely be embedded in the repository.

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Enable **Gmail API**.
4. Configure the OAuth consent screen for an external/testing app and add your Gmail address as a test user.
5. Create an OAuth client with application type **Desktop app**.
6. Download the JSON file and save it as `config/gmail_credentials.json`.
7. In Gmail, create a label named **Job Alerts** and apply it to alerts from LinkedIn Jobs, Wellfound, YC Jobs, Cutshort, Instahyre and any other job source.

On the first run, your browser opens Google's OAuth page. Approve the requested Gmail read and send permissions. The token is stored only in `data/gmail_token.json`, which is ignored by Git.

## Start safely

The default `.env` contains:

```env
DRY_RUN=true
```

Run the complete pipeline:

```powershell
job-automation run
```

Start the dashboard and daily scheduler:

```powershell
job-automation start
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). In dry-run mode, messages are generated and shown but are not sent.

After checking that your Gmail label and profile are correct, enable sending in `.env`:

```env
DRY_RUN=false
```

Restart `job-automation start`. The configured default is eight emails per day, maximum two contacts per company, followed by attempts on days 4 and 9 only when no reply is detected.

## Optional contact discovery

Add a Hunter API key to `.env`:

```env
HUNTER_API_KEY=replace-me
```

Without it, the system uses only addresses explicitly present in the job content or discovered on allowed public company pages.

## Optional RSS/Atom feeds

```env
JOB_FEED_URLS=https://example.com/jobs.xml,https://example.org/internships.atom
```

## Commands

| Command | Purpose |
| --- | --- |
| `job-automation init` | Create private local configuration and initialize SQLite |
| `job-automation run` | Run ingestion, scoring, contact discovery, reply checks and sending once |
| `job-automation start` | Start the dashboard plus daily scheduler |
| `job-automation scheduler` | Run the scheduler without the dashboard |
| `job-automation status` | Print current database counts |

## Safety controls

- Dry-run mode is enabled by default.
- Only syntactically valid corporate email addresses are accepted.
- Personal email providers are blocked.
- Addresses must have a source URL or appear in source content.
- The daily send limit defaults to eight.
- Contacting is capped at two people per company.
- A reply stops the sequence.
- Only two follow-ups are permitted.
- Secrets, OAuth tokens, the local database and personal profile are ignored by Git.
- Public crawling is low-volume and checks `robots.txt`.

## Development

```powershell
pip install -e ".[dev]"
ruff check src tests
pytest --cov=job_automation
```

## Architecture

```text
Gmail alerts / RSS feeds
          |
          v
Parse -> deduplicate -> score -> contact discovery
          |                            |
          +---------- SQLite ----------+
                         |
                         v
               compose -> capped send
                         |
                         v
              reply check -> follow-ups
                         |
                         v
                 local dashboard
```
