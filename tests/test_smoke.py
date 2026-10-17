from bunker.ui.app import create_app


def test_create_app_is_available():
    """Check that the application factory can be imported."""
    assert callable(create_app)
