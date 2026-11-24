# Copyright (C) 2026 Jeff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Preserve and persist the secret used by legacy plaintext pseudonymisation."""

from pymedphys._imports import pytest, toml

from pymedphys._experimental.pseudonymisation import strategy


@pytest.fixture
def pepper_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps({"version": 0, "pseudo": {"epoch_jitter": 17}}))
    monkeypatch.setattr(strategy, "get_config", lambda: toml.load(config_path))
    monkeypatch.setattr(strategy, "get_config_dir", lambda: tmp_path)
    strategy._get_pepper.cache_clear()
    yield config_path
    strategy._get_pepper.cache_clear()


def test_generated_pepper_is_reused_after_clearing_memory_cache(
    pepper_config, monkeypatch
):
    calls = []

    def generate(nbytes):
        calls.append(nbytes)
        return "synthetic-pepper-for-regression-only"

    monkeypatch.setattr(strategy.secrets, "token_urlsafe", generate)
    first = strategy._get_pepper()
    strategy._get_pepper.cache_clear()
    second = strategy._get_pepper()

    assert first == second == b"synthetic-pepper-for-regression-only"
    assert calls == [32]
    config = toml.load(pepper_config)
    assert config["version"] == 0
    assert config["pseudo"]["epoch_jitter"] == 17
    assert config["pseudo"]["pepper"] == first.decode("ascii")


def test_existing_pepper_does_not_trigger_a_new_secret_or_rewrite(
    pepper_config, monkeypatch
):
    original = (
        '[pseudo]\npepper = "existing-synthetic-pepper"\n# preserve this comment\n'
    )
    pepper_config.write_text(original)

    def unexpected_generation(*args):
        pytest.fail("An existing pepper must not be replaced")

    monkeypatch.setattr(strategy.secrets, "token_urlsafe", unexpected_generation)
    assert strategy._get_pepper() == b"existing-synthetic-pepper"
    assert pepper_config.read_text() == original


def test_persistence_failure_does_not_cache_an_unsaved_pepper(
    pepper_config, monkeypatch
):
    monkeypatch.setattr(
        strategy.secrets, "token_urlsafe", lambda _: "synthetic-unsaved-pepper"
    )

    def fail_dump(*args, **kwargs):
        raise OSError("Synthetic write failure")

    monkeypatch.setattr(strategy.toml, "dump", fail_dump)
    with pytest.raises(OSError, match="Synthetic write failure"):
        strategy._get_pepper()
    assert strategy._get_pepper.cache_info().currsize == 0
