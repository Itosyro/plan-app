"""Background workers — scheduler entrypoints for reminders and digests.

Two flavors share the same tick logic:

* :mod:`app.workers.scheduler` — single-shot ``main()`` for an external Cron
  service (Render Starter+, GitHub Actions, system ``cron``).
* :mod:`app.workers.runner` — long-running ``asyncio`` loop embedded in the
  FastAPI process; this is what the free Render web dyno uses.
"""
