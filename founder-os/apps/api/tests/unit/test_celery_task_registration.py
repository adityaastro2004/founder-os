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


def test_worker_import_chain_configures_mappers():
    """Regression (E2E-caught 2026-07-06): in the worker, app.state.models was
    imported without app.models, so the users FK could not resolve and every
    ORM use died with NoReferencedTableError. Simulate the worker chain exactly."""
    from sqlalchemy.orm import configure_mappers

    from app.celery_app import celery

    celery.loader.import_default_modules()
    import app.state.models  # noqa: F401

    configure_mappers()  # raises NoReferencedTableError pre-fix

    from app.database import Base

    assert "users" in Base.metadata.tables
