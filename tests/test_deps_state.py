from src.api.routers import deps


def test_init_state_sets_globals():
    sentinel = object()
    deps.init_state(collector=sentinel)
    assert deps.collector is sentinel
    assert deps.get_collector() is sentinel
    deps.init_state(collector=None)  # reset
    assert deps.collector is None
