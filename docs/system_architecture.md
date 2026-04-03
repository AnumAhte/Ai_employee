# System Architecture — AI Employee Gold Tier

**Version:** 2.0 (Gold Tier)
**Last Updated:** 2026-03-09
**Maintained by:** AI Employee

---

## Table of Contents

1. [Overview](#overview)
2. [Folder Structure](#folder-structure)
3. [MCP Servers](#mcp-servers)
4. [Skills Architecture](#skills-architecture)
5. [Data Flow](#data-flow)
6. [Autonomous Loop (Ralph)](#autonomous-loop-ralph)
7. [Error Handling](#error-handling)
8. [Logging Architecture](#logging-architecture)
9. [Configuration](#configuration)
10. [Lessons Learned](#lessons-learned)

---

## Overview

The AI Employee is a Gold Tier autonomous business management system that operates as a digital employee. It processes incoming tasks, communicates via email and social media, manages accounting in Odoo, and generates executive reports — all with human approval gates for sensitive actions.

```
┌─────────────────────────────────────────────────────────────────┐
│                     AI Employee Gold Tier                        │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  Gmail   │  │  Ralph   │  │  Skills  │  │ MCP Servers  │   │
│  │ Watcher  │→ │  Loop   │→ │  Engine  │→ │  (5 tools)   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
│        │              │             │               │            │
│        ▼              ▼             ▼               ▼            │
│     /inbox       /plans/       /logs/          External APIs     │
│                 /in_progress                  (Odoo, Social)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
/AI_Employee_Vault
│
├── /inbox                    # Incoming tasks and email-to-task conversions
├── /in_progress              # Tasks currently being processed by Ralph
├── /needs_action             # Tasks requiring human review or approval
├── /pending_approval         # External actions awaiting human sign-off
├── /approved                 # Approved actions ready for execution
├── /rejected                 # Rejected actions (archived)
├── /done                     # Completed tasks
│
├── /plans                    # Auto-generated Plan.md files per task
├── /clients                  # Client folders (profile, projects, comms)
├── /reports                  # Generated reports (BI, social, CEO briefing)
├── /docs                     # System documentation
│
├── /mcp_servers              # Python MCP server implementations
│   ├── email_sender.py       # SKILL-009: Email via Gmail SMTP
│   ├── linkedin_poster.py    # SKILL-010: LinkedIn publishing
│   ├── odoo_accounting.py    # Gold: Odoo CRM/accounting
│   ├── meta_social.py        # Gold: Facebook + Instagram
│   └── twitter_poster.py     # Gold: Twitter/X
│
├── /skills                   # Agent skill documentation (markdown)
│   ├── Task_Intake.md        # SKILL-001
│   ├── Planning.md           # SKILL-002
│   ├── Execution.md          # SKILL-003
│   ├── Reporting.md          # SKILL-004
│   ├── Weekly_CEO_Briefing.md # SKILL-005
│   ├── reasoning_planner.md  # SKILL-006
│   ├── Gmail_Watcher.md      # SKILL-007
│   ├── approval_workflow.md  # SKILL-008
│   ├── email_sender_mcp.md   # SKILL-009
│   ├── LinkedIn_Marketing_Post.md # SKILL-010
│   ├── Operations_Agent.md   # SKILL-011 [Gold]
│   ├── Marketing_Agent.md    # SKILL-012 [Gold]
│   ├── Sales_Agent.md        # SKILL-013 [Gold]
│   ├── Business_Intelligence.md # SKILL-014 [Gold]
│   ├── Social_Media_Manager.md  # SKILL-015 [Gold]
│   └── Weekly_Business_Audit.md # SKILL-020 [Gold]
│
├── /logs                     # All system logs
│   ├── gmail_watcher.log
│   ├── email_sender_mcp.log
│   ├── linkedin_post.log
│   ├── odoo_activity.log
│   ├── meta_social.log
│   ├── twitter_activity.log
│   ├── ralph_loop.log
│   ├── marketing_activity.log
│   ├── social_media_manager.log
│   ├── sales_activity.log
│   ├── bi_activity.log
│   ├── weekly_audit.log
│   ├── operations.log
│   └── error_log.md          # Structured failure log (all components)
│
├── /setup                    # Infrastructure setup files
│   └── task_scheduler.xml    # Windows Task Scheduler config
│
├── ralph_loop.py             # Autonomous execution engine
├── gmail_watcher.py          # Gmail IMAP monitor
├── approval_watcher.py       # Approval file watcher
│
├── Dashboard.md              # Live system status
├── Company_Handbook.md       # Business context (read by agents)
├── .mcp.json                 # MCP server registry for Claude Code
├── .env                      # Credentials (not in git)
└── .env.example              # Credential template
```

---

## MCP Servers

Five MCP servers run as stdio processes, registered in `.mcp.json` and loaded automatically by Claude Code.

| Server Name | File | Tools Exposed |
|-------------|------|--------------|
| `email-sender` | `mcp_servers/email_sender.py` | `send_email`, `request_email_approval` |
| `linkedin-poster` | `mcp_servers/linkedin_poster.py` | `linkedin_post` |
| `odoo-accounting` | `mcp_servers/odoo_accounting.py` | `create_customer`, `create_invoice`, `record_payment`, `get_financial_summary` |
| `meta-social` | `mcp_servers/meta_social.py` | `post_facebook_message`, `post_instagram_message`, `get_social_summary` |
| `twitter-poster` | `mcp_servers/twitter_poster.py` | `post_tweet`, `get_twitter_summary` |

### Transport

All servers use **stdio transport** (FastMCP). Claude Code spawns each server as a subprocess and communicates over stdin/stdout.

### Dry-Run Safety

All social/email MCP servers support dry-run mode:

| Server | Env Variable | Default |
|--------|-------------|---------|
| email-sender | `EMAIL_DRY_RUN` | `false` |
| linkedin-poster | `LINKEDIN_DRY_RUN` | `true` |
| meta-social | `META_DRY_RUN` | `true` |
| twitter-poster | `TWITTER_DRY_RUN` | `true` |

---

## Skills Architecture

Skills are markdown documents in `/skills` that define how Claude should behave for specific task types. They are not executable code — they are instructions consumed by Claude Code.

```
Claude Code reads skills → understands workflow → calls MCP tools → logs results
```

### Skill Hierarchy (Gold Tier)

```
┌─────────────────────────────────────┐
│         Orchestration Layer          │
│  Operations_Agent (SKILL-011)        │
│  Ralph Loop (ralph_loop.py)          │
└──────────────┬──────────────────────┘
               │ routes to
    ┌──────────┼──────────────────────┐
    │          │                      │
    ▼          ▼                      ▼
Marketing   Sales Agent         Business Intelligence
Agent       (SKILL-013)         (SKILL-014)
(SKILL-012)
    │
    ▼
Social Media Manager (SKILL-015)
    │
    ▼
MCP Tools (LinkedIn, Twitter, Meta)
```

---

## Data Flow

### Inbound Email → Task
```
Gmail → gmail_watcher.py → /inbox/email_*.md → Ralph Loop → classification → plan → execution
```

### Task → Accounting
```
Task → Sales_Agent → create_customer (Odoo MCP) → create_invoice (Odoo MCP) → log
```

### Task → Social Post
```
Task → Operations_Agent → Marketing_Agent → Social_Media_Manager → MCP tool → log
```

### Task → Report
```
Trigger → Business_Intelligence → Odoo MCP + log parsing → report → Dashboard update
```

### Approval Flow
```
Sensitive action → request_email_approval → /pending_approval → human reviews →
  /approved → approval_watcher.py → send_email → /done
  /rejected → archived
```

---

## Autonomous Loop (Ralph)

`ralph_loop.py` is the autonomous execution engine.

```
┌──────────────────────────────────────────────────────┐
│                    Ralph Loop                         │
│                                                       │
│  1. Scan /inbox for *.md task files                  │
│  2. Move task to /in_progress                        │
│  3. Classify: domain (personal/business) + type      │
│  4. Generate Plan.md in /plans                       │
│  5. Execute steps sequentially                       │
│     ├── Step fails → retry once                      │
│     ├── Still fails → create recovery task           │
│     └── Success → continue                           │
│  6. All steps OK → move to /done                     │
│  7. Any step failed → leave in /in_progress          │
│                       create recovery in /needs_action│
└──────────────────────────────────────────────────────┘
```

**Run modes:**
- `python ralph_loop.py` — process inbox once and exit
- `python ralph_loop.py --loop` — run continuously
- `python ralph_loop.py --loop --interval 900` — every 15 minutes

---

## Error Handling

### Retry Policy

All MCP servers implement **one automatic retry** on failure:
```python
result, err = _call_tool(params)
if err:
    log("RETRY", f"retrying: {err}")
    result, err = _call_tool(params)  # one retry
if err:
    log_error(...)
    _create_recovery_task(...)
```

### Recovery Tasks

When a tool fails after retry, a recovery task is created in `/needs_action`:
```
needs_action/recovery_YYYY-MM-DD_HHMMSS_[component]_[tool].md
```

Recovery tasks include:
- Timestamp
- Failing component and tool
- Error message
- Recommended action

### Error Log

All failures are appended to `logs/error_log.md` in table format:
```
| Timestamp | Component | Action | Status | Details |
```

### Dashboard Notification

Failed tasks update Dashboard.md "Alerts & Blockers" section automatically.

---

## Logging Architecture

### Log Files

| Log File | Written By | Format |
|----------|-----------|--------|
| `gmail_watcher.log` | gmail_watcher.py | `[TS] [GMAIL_WATCHER] [ACTION] - details` |
| `email_sender_mcp.log` | email_sender.py | `[TS] [EMAIL_SENDER_MCP] [ACTION] - details` |
| `linkedin_post.log` | linkedin_poster.py | `[TS] [LINKEDIN_POSTER] [ACTION] - details` |
| `odoo_activity.log` | odoo_accounting.py | `[TS] [ODOO_ACCOUNTING] [ACTION] - details` |
| `meta_social.log` | meta_social.py | `[TS] [META_SOCIAL] [ACTION] - details` |
| `twitter_activity.log` | twitter_poster.py | `[TS] [TWITTER_POSTER] [ACTION] - details` |
| `ralph_loop.log` | ralph_loop.py | `[TS] [RALPH_LOOP] [ACTION] - details` |
| `error_log.md` | All components | Markdown table |

### Structured Log Format

Every log entry contains:
```
[YYYY-MM-DD HH:MM:SS] [COMPONENT_NAME] [ACTION] - details
```

Where ACTION is one of:
- `SENT` / `POSTED` / `CREATED` — success actions
- `DRY_RUN` — simulated actions
- `ERROR` — failures
- `RETRY` — retry attempt
- `RECOVERY_TASK` — recovery file created
- `SUMMARY` — reporting actions

---

## Configuration

### Environment Variables (`.env`)

```
# Gmail
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
GMAIL_CHECK_INTERVAL=300

# Email Sender
EMAIL_DRY_RUN=false

# LinkedIn
LINKEDIN_DRY_RUN=true

# Meta (Facebook + Instagram)
META_DRY_RUN=true
FB_PAGE_ID=
FB_ACCESS_TOKEN=
IG_USER_ID=
IG_ACCESS_TOKEN=

# Twitter/X
TWITTER_DRY_RUN=true
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_TOKEN_SECRET=

# Odoo
ODOO_URL=
ODOO_DB=
ODOO_USERNAME=
ODOO_PASSWORD=
```

### Windows Task Scheduler

Registered as `AIEmployee\EmailWatcher`:
- Runs `watchers/email_watcher.py` every 30 minutes
- Configured in `setup/task_scheduler.xml`
- Python: `C:\Users\CBM\AppData\Local\Programs\Python\Python313\python.exe`

---

## Lessons Learned

### 1. MCP Transport
Use **stdio transport** exclusively. HTTP transport adds unnecessary complexity and port management issues in a local Windows environment.

### 2. Dry-Run Default
Always default social media tools to `DRY_RUN=true`. Accidental live posts cannot be undone. Require explicit `DRY_RUN=false` to publish.

### 3. Retry Once, Not Forever
Implement exactly one retry on MCP tool failures. More retries risk duplicate actions (especially for create operations in Odoo).

### 4. File Pipeline vs. MCP
The file-based pipeline (`/inbox → /in_progress → /done`) handles orchestration. MCP tools handle external side effects. Keep these layers separate.

### 5. Approval for Externals
Any action visible to the outside world (email to client, social post) should route through the approval workflow unless explicitly pre-authorised.

### 6. Git Bash Path Issues
Windows + Git Bash mangles `/c` arguments. Always run system commands via `powershell.exe -Command "..."` from bash scripts.

### 7. Structured Logging
Consistent `[TS] [COMPONENT] [ACTION] - details` format across all components makes log parsing and audit trivial.

### 8. Skill IDs
Maintain a sequential skill ID registry. Check existing IDs before assigning new ones to avoid conflicts.

---

*Last Updated: 2026-03-09*
*AI Employee Gold Tier — Architecture Document*
