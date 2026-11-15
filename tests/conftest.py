"""Safety net for every test: commands never really run unless a test asks for it.

The owner runs ULTRON live on the same laptop. A test that routed sentences
outside dry-run once closed apps, muted audio and took a screenshot. Now every
test runs with the registry in dry-run mode; a test that needs a real handler
(with fakes, like tests/test_windows.py) marks itself @pytest.mark.real_handlers.
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "real_handlers: run command handlers for real (use fakes!)")
    config.addinivalue_line("markers", "needs_model: needs the meaning-matcher model in models/potion-base-8M")


def pytest_collection_modifyitems(config, items):
    """Skip tests that need the 30 MB meaning-matcher model when it is not downloaded (for example on CI)."""
    from ultron.commands import intent
    if intent.model_available():
        return
    skip = pytest.mark.skip(reason="meaning-matcher model not downloaded")
    for item in items:
        if item.get_closest_marker("needs_model"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _dry_run_commands(request):
    if request.node.get_closest_marker("real_handlers"):
        yield
        return
    from ultron.commands import registry
    with registry.dry_run():
        yield
