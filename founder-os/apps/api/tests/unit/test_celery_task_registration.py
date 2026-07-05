"""Regression: the Celery WORKER must register all task modules.

autodiscover_tasks(["app.tasks"]) silently registered nothing (looks for
app.tasks.tasks); found 2026-07-06 when a live worker reported zero registered
tasks. Explicit conf.imports is the fix — this test pins it.
"""


def test_worker_registers_all_task_modules():
    from app.celery_app import celery

    celery.loader.import_default_modules()

    expected = {
        "app.tasks.agent_tasks.run_agent_task",
        "app.tasks.agent_tasks.run_orchestration_task",
        "app.tasks.state_tasks.state_sync_task",
    }
    registered = set(celery.tasks.keys())
    missing = expected - registered
    assert not missing, f"worker would reject these tasks as unregistered: {missing}"
