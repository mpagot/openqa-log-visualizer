import pytest
import yaml
from app import load_configuration


def test_load_configuration_success(tmp_path, app_logger, monkeypatch):
    """Tests successful loading of a valid configuration file."""
    config_content = {
        "autoinst_parser": [
            {
                "name": "test_parser",
                "match_name": ".*(?P<name>test).*",
                "max_jobs_to_explore": 20,
                "channels": [{"name": "test_channel", "pattern": ".*hello.*", "type": "test"}],
            }
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    _, parsers, _, _, max_jobs = load_configuration(app_logger)

    assert len(parsers) == 1
    assert parsers[0]["name"] == "test_parser"
    # Check that regexes have been compiled
    assert hasattr(parsers[0]["match_name"], "search")
    assert hasattr(parsers[0]["channels"][0]["pattern"], "search")

    assert max_jobs == 20

def test_load_configuration_invalid_regex(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if an invalid regex is in the config."""
    config_content = {
        "autoinst_parser": [
            {"name": "bad_parser", "match_name": ".*[", "channels": []}
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_invalid_regex_no_named_group(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if an invalid regex is in the config.
       Here the regexp is invalid as it does not have a named group '(?P<name>...)'
    """
    config_content = {
        "autoinst_parser": [
            {"name": "bad_parser", "match_name": ".*", "channels": []}
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_missing_parser_name(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if a parser is missing a name."""
    config_content = {"autoinst_parser": [{"match_name": ".*", "channels": []}]}
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_missing_channel_name(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if a channel is missing a name."""
    config_content = {
        "autoinst_parser": [
            {"name": "parser1", "channels": [{"type": "error", "pattern": ".*"}]}
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_missing_match_name_group(tmp_path, app_logger, monkeypatch):
    """Tests that the application exits if match_name is missing the 'name' named group."""
    config_content = {
        "autoinst_parser": [
            # This regex is valid, but missing '(?P<name>...)'
            {"name": "bad_parser", "match_name": ".*test.*", "channels": []}
        ]
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_content, f)

    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    with pytest.raises(SystemExit) as e:
        load_configuration(app_logger)
    assert e.value.code == 1


def test_load_configuration_from_env_variable(tmp_path, app_logger, monkeypatch):
    """
    Tests that CONFIG_FILE environment variable is used to load the configuration,
    overriding the default config.yaml in the current directory.
    """
    # Create a default config file with some content in the temp path.
    default_config_content = {
        "autoinst_parser": [
            {
                "name": "default_parser",
                "match_name": ".*(?P<name>default).*",
                "channels": [],
            }
        ]
    }
    (tmp_path / "config.yaml").write_text(yaml.dump(default_config_content))

    # Create a custom config file in a subdirectory with different content.
    custom_config_dir = tmp_path / "custom"
    custom_config_dir.mkdir()
    custom_config_content = {
        "autoinst_parser": [
            {"name": "custom_parser", "match_name": ".*(?P<name>custom).*", "channels": []}
        ]
    }
    custom_config_file = custom_config_dir / "my_config.yaml"
    custom_config_file.write_text(yaml.dump(custom_config_content))

    # Change to the directory with the default config and set the env var
    # to point to the custom config file.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_FILE", str(custom_config_file))

    # Load configuration and assert that the custom one was loaded.
    _, parsers, _, _, _ = load_configuration(app_logger)

    assert len(parsers) == 1
    assert parsers[0]["name"] == "custom_parser"
