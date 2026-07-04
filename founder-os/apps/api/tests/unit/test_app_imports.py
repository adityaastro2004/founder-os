"""The FastAPI app must import and register routes without any services running."""


def test_app_imports_and_has_routes():
    from app.main import app

    assert len(app.routes) > 20  # sanity: all routers registered
