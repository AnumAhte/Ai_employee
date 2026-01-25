# AI Employee Vault

An autonomous AI-powered Business Manager Agent that operates through file-based workflows in an Obsidian vault.

## Overview

AI Employee is a personal business operations manager that:
- Processes tasks through a structured pipeline
- Creates and executes plans autonomously
- Maintains comprehensive documentation and audit trails
- Operates entirely through markdown files

## How It Works

```
/inbox → /needs_action → /in_progress → /done
```

1. **Drop a task** in the `/inbox` folder
2. **AI Employee reads** and analyzes the task
3. **Creates a plan** in the Dashboard
4. **Executes** using available skills
5. **Logs everything** for audit and review

## Folder Structure

```
AI_Employee_Vault/
├── inbox/           # Drop new tasks here
├── needs_action/    # Tasks awaiting planning/approval
├── in_progress/     # Active work
├── done/            # Completed tasks
├── plans/           # Task execution plans
├── skills/          # Agent skill definitions
├── clients/         # Client folders and projects
├── logs/            # Activity logs and reports
├── reports/         # Generated reports (CEO briefings, etc.)
├── Dashboard.md     # Central status display
├── Company_Handbook.md  # Policies and procedures
└── README.md        # This file
```

## Core Skills

| Skill | Purpose |
|-------|---------|
| **Task Intake** | Process incoming tasks from inbox |
| **Planning** | Create step-by-step execution plans |
| **Execution** | Execute plans and manage task lifecycle |
| **Reporting** | Generate reports and maintain logs |
| **Weekly CEO Briefing** | Generate executive summary reports |

## Dashboard

The `Dashboard.md` file serves as the central control panel showing:
- System status
- Task pipeline counts
- Current activity
- Recent completions
- Skill usage statistics
- System health

## Usage

### Adding a Task

Create a markdown file in `/inbox`:

```markdown
---
type: task
priority: high
---

Your task description here.
What needs to be done.
Any specific requirements.
```

### Requesting a CEO Briefing

Create a file in `/inbox`:

```markdown
Generate Weekly CEO Briefing
```

### Viewing Status

Open `Dashboard.md` to see:
- Current task pipeline
- Active work
- Recent completions
- Skill usage

## Logging

All actions are logged in `/logs`:
- `Skill_Usage_Log.md` - Track skill activations
- Daily logs for activity tracking
- Completion reports for finished tasks

## Configuration

Edit `Company_Handbook.md` to customize:
- Priority levels and response times
- Approval requirements
- Communication protocols
- Document standards

## Operating Principles

1. **Transparency** - All actions are logged and auditable
2. **Accuracy** - Verify before acting
3. **Boundaries** - Request approval for uncertain actions
4. **Organization** - Maintain clean folder structure

## Requirements

- Obsidian (recommended for best experience)
- Any markdown editor
- Claude AI for agent operations

## Version

- **Version:** 1.0
- **Initialized:** 2026-01-24
- **Last Updated:** 2026-01-25

## License

MIT License - Use freely for personal or commercial purposes.

---

*Powered by Claude AI | AI Employee v1.0*
