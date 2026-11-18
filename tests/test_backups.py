from __future__ import annotations

from ensemble.backups import backup_file, list_backups
from ensemble.config import default_config, save_config


def test_save_config_backs_up_only_on_change(tmp_path, monkeypatch):
    monkeypatch.setenv("ENSEMBLE_CONFIG_DIR", str(tmp_path / "cfg"))
    config = default_config()
    path = save_config(config)
    assert list_backups(path) == []

    save_config(config)
    assert list_backups(path) == []

    config.prefs.budget_usd = 1.25
    save_config(config)
    backups = list_backups(path)
    assert len(backups) == 1
    assert (backups[0].stat().st_mode & 0o777) == 0o600


def test_backup_pruning_keeps_five(tmp_path):
    target = tmp_path / "thing.json"
    target.write_text("{}", encoding="utf-8")
    for index in range(7):
        target.write_text(f'{{"n": {index}}}\n', encoding="utf-8")
        backup_file(target, keep=5)
    assert len(list_backups(target)) == 5
