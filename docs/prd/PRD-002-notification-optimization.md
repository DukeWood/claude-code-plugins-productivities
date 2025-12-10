# PRD-002: Slack Notification System Optimization

**Document Version:** 1.0
**Created:** 2025-12-10
**Author:** Claude (AI DevMaster)
**Status:** Draft
**Issue:** [#2](https://github.com/DukeWood/claude-code-plugins-productivities/issues/2)

---

## 1. Overview

### 1.1 Problem Statement

The current Slack notification system for Claude Code hooks sends individual notifications for each event without any aggregation, deduplication, or rate limiting. This results in notification spam that reduces the signal-to-noise ratio and degrades user experience, particularly when multiple Claude sessions are running concurrently.

### 1.2 Objective

Optimize the notification system to reduce spam while maintaining timely delivery of important notifications, improving the overall user experience and ensuring critical alerts remain visible.

### 1.3 Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Notifications per hour (multi-session) | 50+ | <20 |
| Duplicate notifications | ~40% | <5% |
| Time to first notification | <1s | <2s |
| User-reported notification fatigue | High | Low |

---

## 2. Background

### 2.1 Current System Architecture

The notification system consists of two implementations:

1. **V1 (Shell-based, Production)**: Immediate notification dispatch via curl
   - `notify-permission.sh` - Permission required notifications
   - `notify-stop.sh` - Task complete notifications
   - No batching, deduplication, or rate limiting

2. **V2 (Python-based, Available)**: Queue-based system with retry logic
   - SQLite database for persistence
   - Notification queue with exponential backoff
   - No aggregation or rate limiting implemented

### 2.2 Current Pain Points

Based on observed Slack channel activity:

```
⏳ Waiting for Input (#1210-9) | People
⏳ Waiting for Input (#1210-11) | People
✅ Task Complete (#1210-13) | People
⏳ Waiting for Input (#1210-14) | People
🔐 Permission Required (#1210-17) | People
🔐 Permission Required (#1210-19) | People
⏳ Waiting for Input (#1210-21) | People
```

**Issues identified:**
- 4 "Waiting for Input" notifications could be consolidated
- 2 "Permission Required" notifications in quick succession
- No context grouping by session or project
- Visual noise reduces attention to critical alerts

---

## 3. Requirements

### 3.1 Functional Requirements

#### FR-1: Rate Limiting
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | System SHALL enforce configurable cooldown periods per notification type | P0 |
| FR-1.2 | Default cooldowns: Permission (30s), Idle (60s), Complete (none) | P0 |
| FR-1.3 | Cooldown SHALL be configurable via `slack-config.json` | P1 |
| FR-1.4 | Rate limiting SHALL be per-session to avoid cross-session suppression | P0 |

#### FR-2: Deduplication
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | System SHALL suppress consecutive identical notification types from same session | P0 |
| FR-2.2 | Suppressed notifications SHALL increment a counter shown in next notification | P1 |
| FR-2.3 | Deduplication window SHALL be configurable (default: 5 minutes) | P2 |

#### FR-3: Time-Window Batching
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | System SHALL support optional batching of notifications within time window | P1 |
| FR-3.2 | Batch window SHALL be configurable (default: 30 seconds) | P1 |
| FR-3.3 | Batched notifications SHALL be grouped by type | P1 |
| FR-3.4 | Batch message format: "⏳ Waiting for Input (4 sessions): #9, #11, #14, #21" | P1 |

#### FR-4: Smart Digest Mode (Optional)
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | System MAY support periodic digest notifications | P3 |
| FR-4.2 | Digest interval SHALL be configurable (default: 5 minutes) | P3 |
| FR-4.3 | Digest SHALL summarize all notification types in one message | P3 |

#### FR-5: Thread-Based Updates (Optional)
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | System MAY support Slack thread replies for status updates | P3 |
| FR-5.2 | Initial notification creates parent message | P3 |
| FR-5.3 | Subsequent updates reply to thread | P3 |

### 3.2 Non-Functional Requirements

#### NFR-1: Performance
| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-1.1 | Hook execution time SHALL remain <100ms | P0 |
| NFR-1.2 | Rate limiting lookup SHALL be O(1) | P0 |
| NFR-1.3 | System SHALL not block Claude Code execution | P0 |

#### NFR-2: Reliability
| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-2.1 | Critical notifications (Permission) SHALL never be permanently suppressed | P0 |
| NFR-2.2 | Rate limiting state SHALL survive process restarts | P1 |
| NFR-2.3 | System SHALL gracefully degrade if state storage fails | P0 |

#### NFR-3: Compatibility
| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-3.1 | Changes SHALL maintain backward compatibility with V1 shell hooks | P0 |
| NFR-3.2 | Configuration format SHALL be backward compatible | P0 |
| NFR-3.3 | Existing webhook URLs SHALL continue to work | P0 |

---

## 4. Technical Design

### 4.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Claude Code Hook Event                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Rate Limiter Module                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ State Store │  │ Cooldown    │  │ Should Send?            │  │
│  │ (SQLite/    │◄─│ Checker     │◄─│ - Check last sent time  │  │
│  │  File)      │  │             │  │ - Check cooldown period │  │
│  └─────────────┘  └─────────────┘  │ - Return yes/no + count │  │
│                                     └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
              [Rate Limited]          [Allowed]
                    │                       │
                    ▼                       ▼
        ┌─────────────────┐    ┌─────────────────────────────────┐
        │ Update Counter  │    │      Deduplication Module       │
        │ (suppressed++)  │    │  - Check if duplicate           │
        └─────────────────┘    │  - Merge with pending if batch  │
                               │  - Update suppressed count      │
                               └─────────────────────────────────┘
                                               │
                                               ▼
                               ┌─────────────────────────────────┐
                               │       Notification Sender       │
                               │  - Build payload with counts    │
                               │  - Send to Slack webhook        │
                               │  - Update last sent timestamp   │
                               └─────────────────────────────────┘
```

### 4.2 Data Model

#### Rate Limit State Schema
```sql
CREATE TABLE rate_limit_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    notification_type TEXT NOT NULL,  -- 'permission', 'idle', 'complete'
    last_sent_at INTEGER NOT NULL,    -- Unix timestamp
    suppressed_count INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(session_id, notification_type)
);

CREATE INDEX idx_rate_limit_session ON rate_limit_state(session_id);
CREATE INDEX idx_rate_limit_type ON rate_limit_state(notification_type);
```

#### Configuration Schema Extension
```json
{
  "webhook_url": "https://hooks.slack.com/services/...",
  "enabled": true,
  "notify_on": {
    "permission_required": true,
    "task_complete": true,
    "input_required": true
  },
  "notify_always": false,
  "rate_limiting": {
    "enabled": true,
    "cooldowns": {
      "permission": 30,
      "idle": 60,
      "complete": 0
    }
  },
  "deduplication": {
    "enabled": true,
    "window_seconds": 300
  },
  "batching": {
    "enabled": false,
    "window_seconds": 30
  }
}
```

### 4.3 Implementation Approach

#### Phase 1: Rate Limiting (P0)
1. Add `lib/rate_limiter.py` module
2. Implement SQLite-based state storage
3. Integrate with existing hook handlers
4. Add configuration options
5. Update V1 shell scripts to call rate limiter

#### Phase 2: Deduplication (P0)
1. Extend rate limiter with dedup logic
2. Track suppressed notification counts
3. Include counts in notification payloads
4. Update Slack message format

#### Phase 3: Batching (P1)
1. Implement batch queue with time windows
2. Add batch aggregation logic
3. Create batch message formatter
4. Optional daemon mode for batch processing

#### Phase 4: Advanced Features (P3)
1. Thread-based updates (requires Slack API changes)
2. Digest mode
3. Per-project/channel routing

---

## 5. User Experience

### 5.1 Before Optimization
```
Channel: #claude-notifications
─────────────────────────────────
⏳ Waiting for Input (#1210-9) | project-a
⏳ Waiting for Input (#1210-11) | project-b
⏳ Waiting for Input (#1210-12) | project-a
🔐 Permission Required (#1210-9) | project-a
⏳ Waiting for Input (#1210-14) | project-c
🔐 Permission Required (#1210-11) | project-b
⏳ Waiting for Input (#1210-9) | project-a
```

### 5.2 After Optimization (Rate Limiting + Dedup)
```
Channel: #claude-notifications
─────────────────────────────────
⏳ Waiting for Input (#1210-9) | project-a
⏳ Waiting for Input (#1210-11) | project-b
🔐 Permission Required (#1210-9) | project-a
⏳ Waiting for Input (#1210-14) | project-c
🔐 Permission Required (#1210-11) | project-b
   └─ (+2 suppressed in last 5 min)
```

### 5.3 After Optimization (With Batching)
```
Channel: #claude-notifications
─────────────────────────────────
📊 Claude Status Update
├─ ⏳ 3 sessions waiting for input: #9, #11, #14
├─ 🔐 2 sessions need permission: #9, #11
└─ Updated: 10:25 AM
```

---

## 6. Configuration Guide

### 6.1 Default Configuration (Conservative)
```json
{
  "rate_limiting": {
    "enabled": true,
    "cooldowns": {
      "permission": 30,
      "idle": 60,
      "complete": 0
    }
  },
  "deduplication": {
    "enabled": true,
    "window_seconds": 300
  },
  "batching": {
    "enabled": false
  }
}
```

### 6.2 Aggressive Spam Reduction
```json
{
  "rate_limiting": {
    "enabled": true,
    "cooldowns": {
      "permission": 60,
      "idle": 120,
      "complete": 0
    }
  },
  "deduplication": {
    "enabled": true,
    "window_seconds": 600
  },
  "batching": {
    "enabled": true,
    "window_seconds": 60
  }
}
```

### 6.3 Minimal (Only Critical)
```json
{
  "rate_limiting": {
    "enabled": true,
    "cooldowns": {
      "permission": 0,
      "idle": 300,
      "complete": 60
    }
  },
  "deduplication": {
    "enabled": true,
    "window_seconds": 900
  }
}
```

---

## 7. Testing Strategy

### 7.1 Unit Tests
- Rate limiter cooldown logic
- Deduplication window calculations
- Configuration parsing and defaults
- State persistence and recovery

### 7.2 Integration Tests
- End-to-end notification flow with rate limiting
- Multi-session concurrent notifications
- State persistence across restarts
- Backward compatibility with V1

### 7.3 Manual Testing Scenarios
1. Single session, rapid permission requests
2. Multiple sessions, mixed notification types
3. Configuration changes mid-session
4. State recovery after crash

---

## 8. Rollout Plan

### Phase 1: Internal Testing
- Deploy to development environment
- Monitor notification volume reduction
- Validate no critical notifications lost

### Phase 2: Opt-in Beta
- Add feature flags for new functionality
- Document configuration options
- Gather user feedback

### Phase 3: General Availability
- Enable rate limiting by default
- Keep batching opt-in
- Monitor and adjust defaults

---

## 9. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Critical notifications suppressed | High | Low | Never suppress first notification; only rate-limit repeats |
| State storage corruption | Medium | Low | Graceful degradation to stateless mode |
| Performance regression | Medium | Low | Benchmark hook execution time; O(1) lookups |
| Configuration complexity | Low | Medium | Sensible defaults; clear documentation |

---

## 10. Open Questions

1. **Q: Should batching be cross-session or per-session?**
   - Recommendation: Cross-session for channel-level summary

2. **Q: How long to retain rate limit state?**
   - Recommendation: 24 hours, auto-cleanup older entries

3. **Q: Should we support per-project notification channels?**
   - Recommendation: Defer to Phase 4 (future enhancement)

---

## 11. References

- [GitHub Issue #2](https://github.com/DukeWood/claude-code-plugins-productivities/issues/2)
- [Slack Block Kit Builder](https://app.slack.com/block-kit-builder)
- [Current V1 Implementation](../hooks/slack/notify-permission.sh)
- [Current V2 Implementation](../hooks/slack/hook.py)

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| Cooldown | Minimum time between notifications of the same type |
| Deduplication | Suppressing identical consecutive notifications |
| Batching | Grouping notifications within a time window |
| Digest | Periodic summary of all notifications |
| Rate Limiting | Controlling notification frequency |

---

## Appendix B: Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-10 | Claude | Initial draft |
