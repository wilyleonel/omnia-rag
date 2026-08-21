from indexer import should_index


def make_dir_conf(**overrides):
    conf = {
        "path": ".",
        "extensions": [".py", ".ts"],
        "exclude": ["node_modules", "dist", ".git"],
    }
    conf.update(overrides)
    return conf


def test_rejects_extension_not_in_list():
    assert should_index("/repo/src/index.js", make_dir_conf()) is False


def test_accepts_matching_extension():
    assert should_index("/repo/src/index.py", make_dir_conf()) is True


def test_rejects_excluded_directory_component():
    assert should_index("/repo/node_modules/pkg/file.py", make_dir_conf()) is False


def test_rejects_default_exclude_file_pattern():
    assert should_index("/repo/src/package-lock.json", make_dir_conf(extensions=[".json"])) is False


def test_rejects_custom_exclude_files_pattern():
    conf = make_dir_conf(exclude_files=["*.generated.py"])
    assert should_index("/repo/src/models.generated.py", conf) is False


def test_accepts_file_not_matching_any_exclude_files_pattern():
    conf = make_dir_conf(exclude_files=["*.generated.py"])
    assert should_index("/repo/src/models.py", conf) is True
