"""Unit tests for config-driven command permission system.

These tests cover the pure functions from ``utils.permissions`` without
requiring a live Discord connection.
"""

import unittest

from utils.config import (
    _VALID_PERMISSION_LEVELS,
    _validate_command_permissions,
    _validate_permission_levels,
    ConfigParseError,
)
from unittest.mock import MagicMock, patch

from utils.permissions import (
    _resolve_user_level,
    _get_command_min_level,
    check_command_permission,
    check_context_permission,
)


# ---------------------------------------------------------------------------
# Permission level name validation
# ---------------------------------------------------------------------------


class TestValidPermissionLevels(unittest.TestCase):
    """The canonical set of valid level names."""

    _EXPECTED = frozenset({"owner", "admin", "user", "guest", "block"})

    def test_valid_names_match_expectation(self) -> None:
        self.assertEqual(_VALID_PERMISSION_LEVELS, self._EXPECTED)

    def test_all_valid_names_are_accepted(self) -> None:
        for name in self._EXPECTED:
            self.assertIn(name, _VALID_PERMISSION_LEVELS)


# ---------------------------------------------------------------------------
# _validate_permission_levels
# ---------------------------------------------------------------------------


_FULL_USERS = {
    "owner": [],
    "admin": [],
    "user": [],
    "guest": [],
    "block": [],
}


class TestValidatePermissionLevels(unittest.TestCase):
    """Structural validation of the permission_levels YAML section."""

    def test_missing_users_raises(self) -> None:
        with self.assertRaisesRegex(ConfigParseError, "users.*required"):
            _validate_permission_levels({})

    def test_missing_level_keys_raises(self) -> None:
        with self.assertRaisesRegex(ConfigParseError, "missing"):
            _validate_permission_levels({"users": {"admin": []}})

    def test_valid_minimal(self) -> None:
        cfg = {
            "users": dict(_FULL_USERS),
            "default_level": "user",
        }
        _validate_permission_levels(cfg)  # should not raise

    def test_users_must_be_dict(self) -> None:
        with self.assertRaisesRegex(ConfigParseError, "must be a mapping"):
            _validate_permission_levels({"users": "not_a_dict"})

    def test_invalid_level_name(self) -> None:
        bad_users = dict(_FULL_USERS)
        bad_users["superadmin"] = [123]
        with self.assertRaisesRegex(ConfigParseError, "not a valid level"):
            _validate_permission_levels({"users": bad_users})

    def test_user_ids_must_be_ints(self) -> None:
        bad_users = dict(_FULL_USERS)
        bad_users["admin"] = ["abc"]
        with self.assertRaisesRegex(ConfigParseError, "non-integer"):
            _validate_permission_levels({"users": bad_users})

    def test_user_ids_must_not_be_bool(self) -> None:
        # bool is an int subclass, must be rejected.
        bad_users = dict(_FULL_USERS)
        bad_users["admin"] = [True]
        with self.assertRaisesRegex(ConfigParseError, "non-integer"):
            _validate_permission_levels({"users": bad_users})

    def test_invalid_default_level(self) -> None:
        with self.assertRaisesRegex(ConfigParseError, "default_level"):
            _validate_permission_levels(
                {"users": dict(_FULL_USERS), "default_level": "superadmin"}
            )

    def test_default_level_must_be_string(self) -> None:
        with self.assertRaisesRegex(ConfigParseError, "default_level"):
            _validate_permission_levels(
                {"users": dict(_FULL_USERS), "default_level": 123}
            )

    def test_empty_users_list_ok(self) -> None:
        _validate_permission_levels({"users": dict(_FULL_USERS)})

    def test_multiple_valid_levels(self) -> None:
        cfg = {
            "users": {
                "owner": [1],
                "admin": [2, 3],
                "user": [],
                "guest": [],
                "block": [99],
            },
            "default_level": "guest",
        }
        _validate_permission_levels(cfg)  # should not raise


# ---------------------------------------------------------------------------
# _validate_command_permissions
# ---------------------------------------------------------------------------


class TestValidateCommandPermissions(unittest.TestCase):
    """Structural validation of the command_permissions YAML section."""

    def test_empty_config_ok(self) -> None:
        _validate_command_permissions({})

    def test_valid_config(self) -> None:
        cfg = {
            "halt": {"min_level": "owner"},
            "switch_llm": {"min_level": "admin"},
        }
        _validate_command_permissions(cfg)  # should not raise

    def test_cmd_value_must_be_dict(self) -> None:
        with self.assertRaisesRegex(ConfigParseError, "must be a mapping"):
            _validate_command_permissions({"halt": "owner"})

    def test_invalid_min_level(self) -> None:
        with self.assertRaisesRegex(ConfigParseError, "min_level"):
            _validate_command_permissions({"halt": {"min_level": "superadmin"}})

    def test_min_level_must_be_string(self) -> None:
        with self.assertRaisesRegex(ConfigParseError, "min_level"):
            _validate_command_permissions({"halt": {"min_level": 4}})

    def test_min_level_block(self) -> None:
        # block is a valid level; it means the command is disabled for everyone.
        cfg = {"halt": {"min_level": "block"}}
        _validate_command_permissions(cfg)  # should not raise


# ---------------------------------------------------------------------------
# _resolve_user_level
# ---------------------------------------------------------------------------


class TestResolveUserLevel(unittest.TestCase):
    """Tests for _resolve_user_level."""

    @staticmethod
    def _cfg(**overrides):
        """Build a level config with sensible defaults."""
        base = {
            "users": dict(_FULL_USERS),
            "default_level": "guest",
        }
        base.update(overrides)
        return base

    def test_falls_back_to_default(self) -> None:
        self.assertEqual(
            _resolve_user_level(self._cfg(), user_id=9999), "guest"
        )

    def test_owner_match(self) -> None:
        cfg = self._cfg()
        cfg["users"]["owner"] = [123]
        self.assertEqual(_resolve_user_level(cfg, user_id=123), "owner")

    def test_admin_match(self) -> None:
        cfg = self._cfg()
        cfg["users"]["admin"] = [456]
        self.assertEqual(_resolve_user_level(cfg, user_id=456), "admin")

    def test_user_match(self) -> None:
        cfg = self._cfg()
        cfg["users"]["user"] = [789]
        self.assertEqual(_resolve_user_level(cfg, user_id=789), "user")

    def test_guest_match(self) -> None:
        cfg = self._cfg()
        cfg["users"]["guest"] = [111]
        self.assertEqual(_resolve_user_level(cfg, user_id=111), "guest")

    def test_block_priority_over_owner(self) -> None:
        cfg = self._cfg()
        cfg["users"]["owner"] = [123]
        cfg["users"]["block"] = [123]
        self.assertEqual(_resolve_user_level(cfg, user_id=123), "block")

    def test_block_priority_over_admin(self) -> None:
        cfg = self._cfg()
        cfg["users"]["admin"] = [123]
        cfg["users"]["block"] = [123]
        self.assertEqual(_resolve_user_level(cfg, user_id=123), "block")

    def test_block_alone(self) -> None:
        cfg = self._cfg()
        cfg["users"]["block"] = [999]
        self.assertEqual(_resolve_user_level(cfg, user_id=999), "block")

    def test_highest_level_wins_among_non_block(self) -> None:
        cfg = self._cfg()
        cfg["users"]["admin"] = [123]
        cfg["users"]["user"] = [123]
        cfg["users"]["guest"] = [123]
        self.assertEqual(_resolve_user_level(cfg, user_id=123), "admin")

    def test_owner_beats_admin(self) -> None:
        cfg = self._cfg()
        cfg["users"]["owner"] = [123]
        cfg["users"]["admin"] = [123]
        self.assertEqual(_resolve_user_level(cfg, user_id=123), "owner")

    def test_user_not_in_any_list_uses_default(self) -> None:
        cfg = self._cfg()
        cfg["users"]["admin"] = [1]
        cfg["users"]["user"] = [2]
        self.assertEqual(_resolve_user_level(cfg, user_id=9999), "guest")

    def test_guest_explicit_overrides_default(self) -> None:
        cfg = self._cfg()
        cfg["users"]["guest"] = [777]
        cfg["default_level"] = "user"
        self.assertEqual(_resolve_user_level(cfg, user_id=777), "guest")


# ---------------------------------------------------------------------------
# _get_command_min_level
# ---------------------------------------------------------------------------


class TestGetCommandMinLevel(unittest.TestCase):
    """Tests for _get_command_min_level."""

    def test_default_guest_when_cmd_missing(self) -> None:
        self.assertEqual(_get_command_min_level({}, "ping"), "guest")

    def test_default_guest_when_cfg_empty(self) -> None:
        self.assertEqual(_get_command_min_level({"ping": {}}, "ping"), "guest")

    def test_respects_configured_min_level(self) -> None:
        cfg = {"halt": {"min_level": "owner"}}
        self.assertEqual(_get_command_min_level(cfg, "halt"), "owner")

    def test_different_commands_different_levels(self) -> None:
        cfg = {
            "halt": {"min_level": "owner"},
            "switch_llm": {"min_level": "admin"},
        }
        self.assertEqual(_get_command_min_level(cfg, "halt"), "owner")
        self.assertEqual(_get_command_min_level(cfg, "switch_llm"), "admin")

    def test_block_level(self) -> None:
        cfg = {"disabled_cmd": {"min_level": "block"}}
        self.assertEqual(_get_command_min_level(cfg, "disabled_cmd"), "block")


# ---------------------------------------------------------------------------
# check_context_permission
# ---------------------------------------------------------------------------


class TestCheckContextPermission(unittest.TestCase):
    """Tests for check_context_permission."""

    def test_user_above_min_context_passes(self) -> None:
        cfg = {
            "users": {**{k: [] for k in _FULL_USERS}, "admin": [123]},
            "min_context_level": "user",
        }
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=cfg,
        ):
            self.assertTrue(check_context_permission(123))

    def test_user_below_min_context_blocked(self) -> None:
        cfg = {
            "users": {**{k: [] for k in _FULL_USERS}, "guest": [456]},
            "min_context_level": "user",
        }
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=cfg,
        ):
            self.assertFalse(check_context_permission(456))

    def test_block_user_always_blocked(self) -> None:
        cfg = {
            "users": {**{k: [] for k in _FULL_USERS}, "owner": [1], "block": [1]},
            "min_context_level": "guest",
        }
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=cfg,
        ):
            self.assertFalse(check_context_permission(1))

    def test_min_context_defaults_to_guest(self) -> None:
        cfg = {
            "users": {**{k: [] for k in _FULL_USERS}, "guest": [789]},
        }
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=cfg,
        ):
            self.assertTrue(check_context_permission(789))

    def test_unlisted_user_uses_default_level(self) -> None:
        cfg = {
            "users": dict(_FULL_USERS),
            "default_level": "user",
            "min_context_level": "user",
        }
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=cfg,
        ):
            self.assertTrue(check_context_permission(9999))


# ---------------------------------------------------------------------------
# check_command_permission
# ---------------------------------------------------------------------------


class TestCheckCommandPermission(unittest.TestCase):
    """Tests for check_command_permission."""

    def _make_interaction(self, user_id: int) -> MagicMock:
        interaction = MagicMock()
        interaction.user.id = user_id
        return interaction

    @staticmethod
    def _level_cfg(owner=(), admin=(), user=(), guest=(), block=(), **kwargs):
        """Build a permission_levels config dict with all five levels."""
        return {
            "users": {
                "owner": list(owner),
                "admin": list(admin),
                "user": list(user),
                "guest": list(guest),
                "block": list(block),
            },
            "default_level": "guest",
            **kwargs,
        }

    def test_owner_allowed_for_owner_command(self) -> None:
        levels = self._level_cfg(owner=[1])
        cmds = {"halt": {"min_level": "owner"}}
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=levels,
        ), patch(
            "utils.permissions.config.get_command_permissions_config",
            return_value=cmds,
        ):
            allowed, msg = self.run_async(
                check_command_permission(self._make_interaction(1), "halt")
            )
            self.assertTrue(allowed)
            self.assertEqual(msg, "")

    def test_admin_denied_for_owner_command(self) -> None:
        levels = self._level_cfg(admin=[2])
        cmds = {"halt": {"min_level": "owner"}}
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=levels,
        ), patch(
            "utils.permissions.config.get_command_permissions_config",
            return_value=cmds,
        ):
            allowed, msg = self.run_async(
                check_command_permission(self._make_interaction(2), "halt")
            )
            self.assertFalse(allowed)
            self.assertIn("owner", msg)

    def test_block_user_denied_even_for_guest_command(self) -> None:
        levels = self._level_cfg(block=[99])
        cmds: dict = {}
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=levels,
        ), patch(
            "utils.permissions.config.get_command_permissions_config",
            return_value=cmds,
        ):
            allowed, msg = self.run_async(
                check_command_permission(self._make_interaction(99), "ping")
            )
            self.assertFalse(allowed)
            self.assertIn("blocked", msg)

    def test_unlisted_command_defaults_to_guest(self) -> None:
        levels = self._level_cfg(guest=[5])
        cmds: dict = {}
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=levels,
        ), patch(
            "utils.permissions.config.get_command_permissions_config",
            return_value=cmds,
        ):
            allowed, msg = self.run_async(
                check_command_permission(self._make_interaction(5), "ping")
            )
            self.assertTrue(allowed)
            self.assertEqual(msg, "")

    def test_unlisted_user_defaults_to_config_level(self) -> None:
        levels = self._level_cfg(default_level="admin")
        cmds = {"switch_llm": {"min_level": "admin"}}
        with patch(
            "utils.permissions.config.get_permission_levels_config",
            return_value=levels,
        ), patch(
            "utils.permissions.config.get_command_permissions_config",
            return_value=cmds,
        ):
            allowed, msg = self.run_async(
                check_command_permission(self._make_interaction(9999), "switch_llm")
            )
            self.assertTrue(allowed)
            self.assertEqual(msg, "")

    def run_async(self, coro):
        """Run an async function synchronously for testing."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # If a loop is already running (e.g. in some test runners), create a new one.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()


if __name__ == "__main__":
    unittest.main()
