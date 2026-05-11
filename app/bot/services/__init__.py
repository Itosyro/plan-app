"""Domain services used by handlers.

Split into submodules for readability (M-3):

* ``users``    — User CRUD + onboarding
* ``inbox``    — InboxEntry + TelegramUpdate idempotency
* ``settings`` — UserSettings queries, mutations, allow-lists
* ``tasks``    — Task/Note/Category/Horizon CRUD + classification + reminders
* ``ai``       — AiRun logging

All public names are re-exported here so existing callers
(``from app.bot.services import ...``) keep working unchanged.
"""

from .ai import log_ai_run as log_ai_run
from .inbox import (
    claim_update as claim_update,
)
from .inbox import (
    is_update_processed as is_update_processed,
)
from .inbox import (
    record_update as record_update,
)
from .inbox import (
    store_inbox_text as store_inbox_text,
)
from .inbox import (
    store_inbox_voice as store_inbox_voice,
)
from .settings import (
    ALLOWED_SETTING_VALUES as ALLOWED_SETTING_VALUES,
)
from .settings import (
    REMINDER_PRESETS as REMINDER_PRESETS,
)
from .settings import (
    get_user_settings as get_user_settings,
)
from .settings import (
    reminder_preset_from_offsets as reminder_preset_from_offsets,
)
from .settings import (
    update_user_settings as update_user_settings,
)
from .tasks import (
    DEFAULT_REMINDER_OFFSETS as DEFAULT_REMINDER_OFFSETS,
)
from .tasks import (
    _escape_like as _escape_like,
)
from .tasks import (
    _select_reminder_offsets as _select_reminder_offsets,
)
from .tasks import (
    _to_naive_utc as _to_naive_utc,
)
from .tasks import (
    delete_task as delete_task,
)
from .tasks import (
    find_task_by_query as find_task_by_query,
)
from .tasks import (
    find_tasks_by_query as find_tasks_by_query,
)
from .tasks import (
    get_all_notes as get_all_notes,
)
from .tasks import (
    get_categories_with_counts as get_categories_with_counts,
)
from .tasks import (
    get_or_create_category as get_or_create_category,
)
from .tasks import (
    get_or_create_horizon as get_or_create_horizon,
)
from .tasks import (
    get_task_by_id as get_task_by_id,
)
from .tasks import (
    get_tasks_by_horizon as get_tasks_by_horizon,
)
from .tasks import (
    get_user_categories as get_user_categories,
)
from .tasks import (
    get_user_categories_full as get_user_categories_full,
)
from .tasks import (
    mark_task_done as mark_task_done,
)
from .tasks import (
    mark_task_undone as mark_task_undone,
)
from .tasks import (
    persist_classification as persist_classification,
)
from .tasks import (
    schedule_reminders as schedule_reminders,
)
from .tasks import (
    update_task_category as update_task_category,
)
from .tasks import (
    update_task_due_at as update_task_due_at,
)
from .tasks import (
    update_task_horizon as update_task_horizon,
)
from .tasks import (
    update_task_priority as update_task_priority,
)
from .tasks import (
    update_task_title as update_task_title,
)
from .users import (
    complete_onboarding as complete_onboarding,
)
from .users import (
    get_or_create_user as get_or_create_user,
)
from .users import (
    is_valid_timezone as is_valid_timezone,
)
