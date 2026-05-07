"""Cron entry point.

Phase 0 placeholder. Phase 4 will:
- read `reminders` where `fire_at <= now()`,
- send Telegram messages,
- update statuses,
- emit morning/evening digests per user settings,
- retry failed `processing_jobs`.
"""

from __future__ import annotations


def main() -> int:
    """Tick the scheduler once. Render cron invokes this every minute."""
    # NOTE(phase0): no-op until Phase 4.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
