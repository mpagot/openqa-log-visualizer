import pytest
import yaml
from app import load_configuration


def test_load_configuration_success(tmp_path, app_logger, monkeypatch):
    """Tests successful loading of a valid configuration file."""
    config_content = {
        "max_jobs_to_explore": 20,
        "log_parsers": [
            {
                "name": "Autoinst Log",
                "log_filename": "autoinst-log.txt",
                "patterns": [
                    {
                        "name": "test_parser",
                        "match_name": ".*(?P<name>test).*",
                        "channels": [
                            {
                                "name": "test_channel",
                                "pattern": ".*hello.*",
                                "type": "test",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    _, _, log_parsers, _, _, max_jobs = load_configuration(app_logger)

    assert len(log_parsers) == 1
    assert log_parsers[0]["name"] == "Autoinst Log"
    assert log_parsers[0]["log_filename"] == "autoinst-log.txt"
    patterns = log_parsers[0]["patterns"]
    assert len(patterns) == 1
    assert patterns[0]["name"] == "test_parser"
    # Check that regexes have been compiled
    assert hasattr(patterns[0]["match_name"], "search")
    assert hasattr(patterns[0]["channels"][0]["pattern"], "search")

    assert max_jobs == 20


def test_load_configuration_invalid_regex(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if an invalid regex is in the config."""
    config_content = {
        "log_parsers": [
            {
                "name": "Autoinst Log",
                "log_filename": "autoinst-log.txt",
                "patterns": [
                    {"name": "bad_parser", "match_name": ".*[", "channels": []}
                ],
            }
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_invalid_regex_no_named_group(
    tmp_path, app_logger, monkeypatch
):
    """Tests that the application exits if an invalid regex is in the config.
    Here the regexp is invalid as it does not have a named group '(?P<name>...)'
    """
    config_content = {
        "log_parsers": [
            {
                "name": "Autoinst Log",
                "log_filename": "autoinst-log.txt",
                "patterns": [
                    {"name": "bad_parser", "match_name": ".*", "channels": []}
                ],
            }
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_missing_parser_name(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if a parser is missing a name."""
    config_content = {
        "log_parsers": [
            {
                "name": "Autoinst Log",
                "log_filename": "autoinst-log.txt",
                "patterns": [{"match_name": ".*", "channels": []}],
            }
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_missing_channel_name(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if a channel is missing a name."""
    config_content = {
        "log_parsers": [
            {
                "name": "Autoinst Log",
                "log_filename": "autoinst-log.txt",
                "patterns": [
                    {
                        "name": "parser1",
                        "channels": [{"type": "error", "pattern": ".*"}],
                    }
                ],
            }
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_missing_match_name_group(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if match_name is missing the 'name' named group."""
    config_content = {
        "log_parsers": [
            {
                "name": "Autoinst Log",
                "log_filename": "autoinst-log.txt",
                "patterns": [
                    # This regex is valid, but missing '(?P<name>...)'
                    {"name": "bad_parser", "match_name": ".*test.*", "channels": []}
                ],
            }
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_from_env_variable(tmp_path, app_logger, monkeypatch):
    """
    Tests that OQTV_CONFIG_FILE environment variable is used to load the configuration,
    overriding the default config.yaml in the current directory.
    """
    # Create a default config file with some content in the temp path.
    default_config_content = {
        "log_parsers": [
            {
                "name": "Autoinst Log",
                "log_filename": "autoinst-log.txt",
                "patterns": [
                    {
                        "name": "default_parser",
                        "match_name": ".*(?P<name>default).*",
                        "channels": [],
                    }
                ],
            }
        ]
    }
    (tmp_path / "config.yaml").write_text(yaml.dump(default_config_content))

    # Create a custom config file in a subdirectory with different content.
    custom_config_dir = tmp_path / "custom"
    custom_config_dir.mkdir()
    custom_config_content = {
        "log_parsers": [
            {
                "name": "Autoinst Log",
                "log_filename": "autoinst-log.txt",
                "patterns": [
                    {
                        "name": "custom_parser",
                        "match_name": ".*(?P<name>custom).*",
                        "channels": [],
                    }
                ],
            }
        ]
    }
    custom_config_file = custom_config_dir / "my_config.yaml"
    custom_config_file.write_text(yaml.dump(custom_config_content))

    # Change to the directory with the default config and set the env var
    # to point to the custom config file.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OQTV_CONFIG_FILE", str(custom_config_file))

    # Load configuration and assert that the custom one was loaded.
    _, _, log_parsers, _, _, _ = load_configuration(app_logger)

    assert len(log_parsers) == 1
    assert log_parsers[0]["name"] == "Autoinst Log"
    patterns = log_parsers[0]["patterns"]
    assert len(patterns) == 1
    assert patterns[0]["name"] == "custom_parser"


def test_load_configuration_cache_full(tmp_path, app_logger, monkeypatch):
    """Tests that cache_dir and cache_max_size are read correctly."""
    config_content = {
        "cache": {"cache_dir": "/tmp/custom_cache", "cache_max_size": 1024}
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    CACHE_DIR, CACHE_MAX_SIZE, _, _, _, _ = load_configuration(app_logger)

    assert CACHE_DIR == "/tmp/custom_cache"
    assert CACHE_MAX_SIZE == 1024


def test_load_configuration_cache_only_dir(tmp_path, app_logger, monkeypatch):
    """Tests that only cache_dir is read correctly."""
    config_content = {"cache": {"cache_dir": "/tmp/other_cache"}}
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    CACHE_DIR, CACHE_MAX_SIZE, _, _, _, _ = load_configuration(app_logger)

    assert CACHE_DIR == "/tmp/other_cache"
    assert CACHE_MAX_SIZE is None


def test_load_configuration_cache_only_size(tmp_path, app_logger, monkeypatch):
    """Tests that only cache_max_size is read correctly."""
    config_content = {"cache": {"cache_max_size": 512}}
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    CACHE_DIR, CACHE_MAX_SIZE, _, _, _, _ = load_configuration(app_logger)

    assert CACHE_DIR == "./.cache"  # Default value
    assert CACHE_MAX_SIZE == 512


def test_load_configuration_cache_empty(tmp_path, app_logger, monkeypatch):
    """Tests that an empty cache block results in default values."""
    config_content = {"cache": {}}
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    CACHE_DIR, CACHE_MAX_SIZE, _, _, _, _ = load_configuration(app_logger)

    assert CACHE_DIR == "./.cache"
    assert CACHE_MAX_SIZE is None


def test_load_configuration_no_cache(tmp_path, app_logger, monkeypatch):
    """Tests that no cache block results in default values."""
    config_content = {}
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    CACHE_DIR, CACHE_MAX_SIZE, _, _, _, _ = load_configuration(app_logger)

    assert CACHE_DIR == "./.cache"
    assert CACHE_MAX_SIZE is None


def test_load_configuration_backward_compatibility(tmp_path, app_logger, monkeypatch):
    """
    Tests that the old `autoinst_parser` config format is correctly
    converted to the new `log_parsers` format for backward compatibility.
    """
    # Old format configuration
    config_content = {
        "autoinst_parser": [
            {
                "name": "legacy_parser",
                "match_name": ".*(?P<name>legacy).*",
                "channels": [
                    {
                        "name": "legacy_channel",
                        "pattern": ".*hello.*",
                        "type": "test",
                    }
                ],
            }
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("OQTV_CONFIG_FILE", str(config_file))
    _, _, log_parsers, _, _, _ = load_configuration(app_logger)

    # Assert that it was converted to the new structure
    assert len(log_parsers) == 1
    assert log_parsers[0]["name"] == "Autoinst Log"
    assert log_parsers[0]["log_filename"] == "autoinst-log.txt"

    # The original patterns should be preserved under the 'patterns' key
    patterns = log_parsers[0]["patterns"]
    assert len(patterns) == 1
    assert patterns[0]["name"] == "legacy_parser"
    assert hasattr(patterns[0]["match_name"], "search")  # Check for compilation
    assert patterns[0]["channels"][0]["name"] == "legacy_channel"
