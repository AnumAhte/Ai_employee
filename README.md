# AI Employee Vault

An autonomous AI-powered business manager that monitors your email, manages accounting, publishes social media content, and runs your business operations — with human approval gates for every external action.

**Version:** 2.0 — Gold Tier
**Platform:** Windows 10 + Python 3.13 + Claude Sonnet 4.6
**Last Updated:** 2026-04-03

---

## What It Can Do

### Automatically (no human input needed)
- Monitor Gmail every 5 minutes and convert matching emails into tasks
- Classify, plan, and execute tasks through a structured pipeline
- Create customers, invoices, and record payments in Odoo
- Generate financial summaries, CEO briefings, and BI reports
- Post drafts to social media platforms (dry-run by default — safe)
- Log every action across 13 separate log files
- Retry failed actions once and escalate to `/needs_action` if unresolved

### With Your Approval
All external-facing actions pause and wait for you to move a file from `/pending_approval` to `/approved`:

| Action | Trigger |
|---|---|
| Send an email | Move approval file → `/approved` |
| Post on LinkedIn | Move approval file → `/approved` |
| Post on Twitter/X | Move approval file → `/approved` |
| Post on Facebook / Instagram | Move approval file → `/approved` |
| Send a sales proposal | Move approval file → `/approved` |

---

## System Architecture

```
Gmail Inbox
    ↓ (IMAP, every 5 min)
Gmail Watcher  ──── filters by keyword / sender
    ↓
/inbox  →  Ralph Loop (classify + plan + execute)
    ↓                        ↓
/in_progress          /needs_action (blockers)
    ↓
/done

External Actions:
Ralph Loop → /pending_approval → [Human Approval] → Approval Watcher → Execute
```

### Core Components

| Component | File | Purpose |
|---|---|---|
| **Gmail Watcher** | `gmail_watcher.py` | IMAP monitoring, email-to-task conversion |
| **Ralph Loop** | `ralph_loop.py` | Autonomous task classification and execution engine |
| **Approval Watcher** | `approval_watcher.py` | Executes human-approved external actions |
| **Dashboard** | `Dashboard.md` | Real-time system status and task pipeline view |

---

## MCP Servers (External Integrations)

Five MCP servers run as subprocesses and expose tools to Claude via the MCP protocol (registered in `.mcp.json`):

| Server | File | Tools |
|---|---|---|
| **Email Sender** | `mcp_servers/email_sender.py` | `send_email`, `request_email_approval` |
| **Odoo Accounting** | `mcp_servers/odoo_accounting.py` | `create_customer`, `create_invoice`, `record_payment`, `get_financial_summary` |
| **LinkedIn Poster** | `mcp_servers/linkedin_poster.py` | `linkedin_post` |
| **Twitter Poster** | `mcp_servers/twitter_poster.py` | `post_tweet`, `get_twitter_summary` |
| **Meta Social** | `mcp_servers/meta_social.py` | `post_facebook_message`, `post_instagram_message`, `get_social_summary` |

All social media tools default to **dry-run mode** — they simulate actions without publishing until you set `DRY_RUN=false` in `.env`.

---

## Specialist Agents (Skills)

16 skills are defined in `/skills/`. Each is a markdown instruction set that guides Claude's reasoning for a specific domain:

| Agent | Skill File | Handles |
|---|---|---|
| **Operations Agent** | `Operations_Agent.md` | Task routing, day-to-day operations, delegation |
| **Marketing Agent** | `Marketing_Agent.md` | Social content creation, platform-specific posting |
| **Sales Agent** | `Sales_Agent.md` | Lead qualification, proposals, customer onboarding |
| **Business Intelligence** | `Business_Intelligence.md` | Odoo + social data aggregation, insight reports |
| **Social Media Manager** | `Social_Media_Manager.md` | Content calendar, cross-platform strategy |
| **Weekly Business Audit** | `Weekly_Business_Audit.md` | CEO-level weekly briefing generation |
| **Email Sender MCP** | `email_sender_mcp.md` | Email tool interface and approval workflow |
| **LinkedIn Marketing** | `LinkedIn_Marketing_Post.md` | LinkedIn content and publishing |
| **Approval Workflow** | `approval_workflow.md` | Approval request management |

---

## Folder Structure

```
AI_Employee_Vault/
├── inbox/                  # New tasks land here (gitignored)
├── in_progress/            # Active tasks (gitignored)
├── done/                   # Completed tasks (gitignored)
├── pending_approval/       # Awaiting human approval (gitignored)
├── approved/               # Human-approved actions (gitignored)
├── rejected/               # Rejected actions (gitignored)
├── needs_action/           # Escalations and blockers (gitignored)
├── plans/                  # Task execution plans (gitignored)
├── reports/                # Generated reports (gitignored)
├── logs/                   # All activity logs (gitignored)
├── mcp_servers/            # MCP server Python files
├── skills/                 # Agent skill definitions
├── setup/
│   ├── odoo/
│   │   └── docker-compose.yml   # Odoo + PostgreSQL stack
│   └── task_scheduler.xml       # Windows Task Scheduler config
├── gmail_watcher.py        # Email monitoring daemon
├── ralph_loop.py           # Autonomous task execution engine
├── approval_watcher.py     # Approval workflow executor
├── Dashboard.md            # Live system status
├── .mcp.json               # MCP server registry
├── .env.example            # Environment variable template
└── README.md
```

> **Note:** `/inbox`, `/logs`, `/in_progress`, `/done`, `/pending_approval`, `/approved`, `/rejected`, `/needs_action`, `/plans`, and `/reports` are all gitignored — they contain private operational data and email content.

---

## Setup

### 1. Clone & Install Dependencies

```bash
git clone <your-repo-url>
cd AI_Employee_Vault
pip install python-dotenv requests mcp fastmcp tweepy
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Key variables:

```env
# Gmail
GMAIL_ADDRESS=your@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
FILTER_KEYWORDS=TASK,CLIENT,INVOICE
FILTER_SENDERS=trusted@example.com

# Odoo
ODOO_URL=http://localhost:8069
ODOO_DB=mycompany
ODOO_USERNAME=admin@example.com
ODOO_PASSWORD=yourpassword
ODOO_DRY_RUN=false

# Social Media (all safe by default)
LINKEDIN_DRY_RUN=true
TWITTER_DRY_RUN=true
META_DRY_RUN=true
```

### 3. Start Odoo (Accounting Backend)

```bash
cd setup/odoo
docker compose up -d
# Open http://localhost:8069 → create database → install CRM + Invoicing
```

### 4. Run the Watchers

```bash
# Email monitoring (runs every 5 min)
python gmail_watcher.py

# Task execution engine (runs continuously)
python ralph_loop.py --loop

# Approval watcher (monitors /pending_approval)
python approval_watcher.py
```

Or register `gmail_watcher.py` with Windows Task Scheduler using `setup/task_scheduler.xml`.

---

## Email Filtering

The Gmail Watcher only creates tasks for emails that match at least one rule:

| Rule | Default |
|---|---|
| Subject contains keyword | `TASK`, `CLIENT`, `INVOICE` |
| Sender in approved list | Your own Gmail address |

Everything else is logged to `logs/email_ignored.log` and skipped.

To customize, add to `.env`:
```env
FILTER_KEYWORDS=TASK,CLIENT,INVOICE,URGENT
FILTER_SENDERS=boss@company.com,client@acme.com
```

---

## Approval Workflow

When an agent wants to take an external action:

1. Creates a markdown file in `/pending_approval/` with request ID, action details, content preview, and risk assessment
2. **You review the file**
3. Move it to `/approved` → Approval Watcher executes the action
4. Move it to `/rejected` → Action is archived and skipped

---

## Logging

Every component writes to its own log file in `/logs/`:

| Log | Component |
|---|---|
| `gmail_watcher.log` | Email intake |
| `email_sender_mcp.log` | Email sending |
| `email_processed.log` | Emails that passed the filter |
| `email_ignored.log` | Emails that were skipped |
| `odoo_activity.log` | Accounting operations |
| `linkedin_post.log` | LinkedIn publishing |
| `twitter_activity.log` | Twitter/X publishing |
| `meta_social.log` | Facebook/Instagram publishing |
| `ralph_loop.log` | Task processing |
| `error_log.md` | Centralized error registry |

---

## Safety Features

- **Dry-run defaults** — All social media tools simulate posting until explicitly enabled
- **Approval gates** — No email or social post goes out without human sign-off
- **One-retry policy** — Prevents duplicate invoices, double-sends
- **No secrets in git** — `.env` is gitignored; runtime folders are gitignored
- **Email validation** — Regex check before any send attempt
- **Session resilience** — Odoo MCP auto-re-authenticates on session expiry

---

## Requirements

- Python 3.11+
- Docker Desktop (for Odoo)
- Gmail account with App Password enabled (2FA required)
- Claude Code (for agent operations via MCP)
- API credentials for any social platforms you want to enable

---

## License

MIT License — use freely for personal or commercial purposes.

---

*Powered by Claude Sonnet 4.6 | AI Employee Vault v2.0*
