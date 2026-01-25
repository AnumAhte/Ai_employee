# Task Intake Skill

**Skill ID:** SKILL-001
**Status:** Active
**Last Updated:** 2026-01-24

---

## Purpose

Process incoming tasks from the `/inbox` folder and prepare them for action.

---

## Workflow

```mermaid
graph LR
    A[New file in /inbox] --> B[Read & Analyze]
    B --> C[Summarize Task]
    C --> D[Move to /needs_action]
    D --> E[Update Dashboard]
```

---

## Procedure

### Step 1: Monitor Inbox
- [ ] Scan `/inbox` folder for new files
- [ ] Identify file type and content

### Step 2: Analyze Content
- [ ] Read file contents
- [ ] Extract key information:
  - Task description
  - Urgency level
  - Required resources
  - Deadline (if specified)
  - Client association (if any)

### Step 3: Create Summary
- [ ] Write summary header in the task file
- [ ] Tag with appropriate labels
- [ ] Assign priority: `#high`, `#medium`, `#low`

### Step 4: Move to Needs_Action
- [ ] Transfer file from `/inbox` to `/needs_action`
- [ ] Preserve original content
- [ ] Add intake timestamp

### Step 5: Update Dashboard
- [ ] Log new task in Dashboard.md
- [ ] Update task counters

---

## File Naming Convention

```
YYYY-MM-DD_TaskTitle_Priority.md
```

**Example:** `2026-01-24_Client_Proposal_high.md`

---

## Trigger Conditions

- New file detected in `/inbox`
- Manual request to process inbox
- Scheduled scan (if configured)

---

## Output

- Processed task file in `/needs_action`
- Updated Dashboard.md
- Log entry in `/logs`

---

## Related Skills

- [[Planning]] - Next step after intake
- [[Reporting]] - Status updates

---

*This skill is managed by AI Employee v1.0*
