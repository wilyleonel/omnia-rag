import yaml

import indexer


def test_load_config_returns_default_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "CONFIG_FILE", str(tmp_path / "omnia.yaml"))

    config = indexer.load_config()

    assert config == {"active_space": "default", "spaces": {"default": {"directories": []}}}


def test_load_config_migrates_legacy_directories_key(tmp_path, monkeypatch):
    config_file = tmp_path / "omnia.yaml"
    config_file.write_text(yaml.dump({"directories": [{"path": "../frontend"}]}))
    monkeypatch.setattr(indexer, "CONFIG_FILE", str(config_file))

    config = indexer.load_config()

    assert "directories" not in config
    assert config["active_space"] == "default"
    assert config["spaces"]["default"]["directories"] == [{"path": "../frontend"}]

    # La migración también debe persistirse a disco
    persisted = yaml.safe_load(config_file.read_text())
    assert "directories" not in persisted
    assert persisted["spaces"]["default"]["directories"] == [{"path": "../frontend"}]


def test_load_config_fills_missing_spaces_and_active_space(tmp_path, monkeypatch):
    config_file = tmp_path / "omnia.yaml"
    config_file.write_text(yaml.dump({"some_other_key": True}))
    monkeypatch.setattr(indexer, "CONFIG_FILE", str(config_file))

    config = indexer.load_config()

    assert config["spaces"] == {"default": {"directories": []}}
    assert config["active_space"] == "default"


def test_load_config_leaves_already_migrated_config_untouched(tmp_path, monkeypatch):
    config_file = tmp_path / "omnia.yaml"
    original = {"active_space": "work", "spaces": {"work": {"directories": [{"path": "x"}]}}}
    config_file.write_text(yaml.dump(original))
    monkeypatch.setattr(indexer, "CONFIG_FILE", str(config_file))

    config = indexer.load_config()

    assert config == original
