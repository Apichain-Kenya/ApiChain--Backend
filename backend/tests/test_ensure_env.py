# tests/test_ensure_env.py
from types import SimpleNamespace
import app.routers.batch as batch_mod
from app.routers.batch import _ensure_environmental_data


class _Query:
    def __init__(self, result): self._result = result
    def filter(self, *a, **k): return self
    def first(self): return self._result


class _DB:
    def __init__(self, env_existing, apiary):
        self._env, self._apiary = env_existing, apiary
        self.added = []
    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "EnvironmentalData": return _Query(self._env)
        if name == "ApiaryLocation": return _Query(self._apiary)
        return _Query(None)
    def add(self, row): self.added.append(row)
    def flush(self): pass


def test_returns_existing_env_without_fetching(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(batch_mod, "fetch_environment_snapshot",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {})
    env = SimpleNamespace(batch_id=1)
    db = _DB(env_existing=env, apiary=SimpleNamespace(latitude=-0.5, longitude=37.0))
    batch = SimpleNamespace(id=1, apiary_id=4)
    assert _ensure_environmental_data(db, batch) is env
    assert called["n"] == 0  # did not fetch


def test_fetches_and_persists_when_missing(monkeypatch):
    monkeypatch.setattr(batch_mod, "fetch_environment_snapshot",
                        lambda lat, lon: {"temperature": 22.0, "humidity": 65.0,
                                          "rainfall": 80.0, "pressure": 1013.0,
                                          "cloud_cover": 10.0, "wind_speed": 3.0,
                                          "weather_source": "open-meteo"})
    db = _DB(env_existing=None, apiary=SimpleNamespace(latitude=-0.5, longitude=37.0))
    batch = SimpleNamespace(id=1, apiary_id=4)
    env = _ensure_environmental_data(db, batch)
    assert env is not None and env.temperature == 22.0
    assert len(db.added) == 1


def test_no_apiary_id_returns_none():
    db = _DB(env_existing=None, apiary=None)
    batch = SimpleNamespace(id=1, apiary_id=None)
    assert _ensure_environmental_data(db, batch) is None


def test_apiary_not_found_returns_none():
    db = _DB(env_existing=None, apiary=None)
    batch = SimpleNamespace(id=1, apiary_id=99)
    assert _ensure_environmental_data(db, batch) is None
