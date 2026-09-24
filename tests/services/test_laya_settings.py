from pathlib import Path
from deeptutor.services.config.runtime_settings import (
    DEFAULT_SYSTEM_SETTINGS,
    RuntimeSettingsService,
)


def test_default_system_settings_include_laya_config():
    assert "kb_preseed_mode" in DEFAULT_SYSTEM_SETTINGS
    assert DEFAULT_SYSTEM_SETTINGS["kb_preseed_mode"] == "off"
    assert "laya_service_url" in DEFAULT_SYSTEM_SETTINGS
    assert DEFAULT_SYSTEM_SETTINGS["laya_service_url"] == "http://deeptutor-laya:8000/v1/decide"
    assert "laya_threshold" in DEFAULT_SYSTEM_SETTINGS
    assert DEFAULT_SYSTEM_SETTINGS["laya_threshold"] == 0.70


def test_runtime_settings_service_normalizes_laya(tmp_path: Path):
    service = RuntimeSettingsService(tmp_path / "settings")
    raw = {
        "kb_preseed_mode": "AUTO",
        "laya_service_url": "http://localhost:8002/v1/decide",
        "laya_threshold": 1.5,  # should clamp to 1.0
    }
    saved = service.save_system(raw)
    assert saved["kb_preseed_mode"] == "auto"
    assert saved["laya_service_url"] == "http://localhost:8002/v1/decide"
    assert saved["laya_threshold"] == 1.0


def test_runtime_settings_service_invalid_mode_defaults_to_off(tmp_path: Path):
    service = RuntimeSettingsService(tmp_path / "settings")
    raw = {
        "kb_preseed_mode": "invalid_mode",
        "laya_threshold": -0.5,  # should clamp to 0.0
    }
    saved = service.save_system(raw)
    assert saved["kb_preseed_mode"] == "off"
    assert saved["laya_threshold"] == 0.0
