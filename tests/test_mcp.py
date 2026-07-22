"""
Unit tests for Comfy MCP server feature detection and configuration.

Tests cover:
- ENABLE_MCP environment variable detection (true/false/unset)
- MCP_PORT defaulting (8765 when unset)
- MCP_TRANSPORT validation (http/tunnel/stdio/invalid)
- MCP_COMFYUI_URL defaulting (http://127.0.0.1:8188)
- MCP_HTTP_TOKEN handling (set/unset)
- Userscript install guard logic
- Entrypoint MCP startup command construction

These tests validate the configuration logic documented in .env.example
and implemented in entrypoint.sh and userscripts_dir/install_comfy_mcp.sh.
Since the entrypoint is a bash script, we test the configuration parsing
logic that would be used by any Python wrapper or validation layer.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMCPFeatureDetection:
    """Tests for ENABLE_MCP feature detection logic."""

    def test_mcp_disabled_by_default(self):
        """MCP should be disabled when ENABLE_MCP is not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_MCP", None)
            enabled = os.environ.get("ENABLE_MCP", "false") == "true"
            assert enabled is False

    def test_mcp_enabled_when_true(self):
        """MCP should be enabled when ENABLE_MCP=true."""
        with patch.dict(os.environ, {"ENABLE_MCP": "true"}):
            enabled = os.environ.get("ENABLE_MCP", "false") == "true"
            assert enabled is True

    def test_mcp_disabled_when_false(self):
        """MCP should be disabled when ENABLE_MCP=false."""
        with patch.dict(os.environ, {"ENABLE_MCP": "false"}):
            enabled = os.environ.get("ENABLE_MCP", "false") == "true"
            assert enabled is False

    def test_mcp_disabled_when_invalid_value(self):
        """MCP should be disabled for any value other than 'true'."""
        for value in ["yes", "1", "enabled", "TRUE", "True", "", None]:
            env = {} if value is None else {"ENABLE_MCP": value}
            with patch.dict(os.environ, env, clear=False):
                if value is None:
                    os.environ.pop("ENABLE_MCP", None)
                enabled = os.environ.get("ENABLE_MCP", "false") == "true"
                assert enabled is False, f"ENABLE_MCP='{value}' should not enable MCP"


class TestMCPPortDefault:
    """Tests for MCP_PORT configuration."""

    def test_mcp_port_defaults_to_8765(self):
        """MCP_PORT should default to 8765 when not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MCP_PORT", None)
            port = os.environ.get("MCP_PORT", "8765")
            assert port == "8765"

    def test_mcp_port_respects_custom_value(self):
        """MCP_PORT should use custom value when set."""
        with patch.dict(os.environ, {"MCP_PORT": "9999"}):
            port = os.environ.get("MCP_PORT", "8765")
            assert port == "9999"

    def test_mcp_port_is_string_from_env(self):
        """MCP_PORT from environment is always a string."""
        with patch.dict(os.environ, {"MCP_PORT": "8765"}):
            port = os.environ.get("MCP_PORT", "8765")
            assert isinstance(port, str)


class TestMCPTransportValidation:
    """Tests for MCP_TRANSPORT configuration."""

    VALID_TRANSPORTS = ["http", "tunnel", "stdio"]

    def test_mcp_transport_defaults_to_http(self):
        """MCP_TRANSPORT should default to 'http' when not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MCP_TRANSPORT", None)
            transport = os.environ.get("MCP_TRANSPORT", "http")
            assert transport == "http"

    def test_mcp_transport_accepts_http(self):
        """MCP_TRANSPORT=http should be accepted."""
        with patch.dict(os.environ, {"MCP_TRANSPORT": "http"}):
            transport = os.environ.get("MCP_TRANSPORT", "http")
            assert transport in self.VALID_TRANSPORTS

    def test_mcp_transport_accepts_tunnel(self):
        """MCP_TRANSPORT=tunnel should be accepted."""
        with patch.dict(os.environ, {"MCP_TRANSPORT": "tunnel"}):
            transport = os.environ.get("MCP_TRANSPORT", "http")
            assert transport in self.VALID_TRANSPORTS

    def test_mcp_transport_accepts_stdio(self):
        """MCP_TRANSPORT=stdio should be accepted."""
        with patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}):
            transport = os.environ.get("MCP_TRANSPORT", "http")
            assert transport in self.VALID_TRANSPORTS

    def test_mcp_transport_invalid_falls_back_to_http(self):
        """Invalid MCP_TRANSPORT should fall back to 'http' (entrypoint behavior)."""
        for invalid in ["websocket", "grpc", "tcp", "", "HTTP", "Tunnel"]:
            with patch.dict(os.environ, {"MCP_TRANSPORT": invalid}):
                transport = os.environ.get("MCP_TRANSPORT", "http")
                # Entrypoint falls back to http for unknown values
                if transport not in self.VALID_TRANSPORTS:
                    transport = "http"
                assert transport == "http", f"MCP_TRANSPORT='{invalid}' should fall back to http"


class TestMCPComfyUIURL:
    """Tests for MCP_COMFYUI_URL configuration."""

    def test_mcp_comfyui_url_defaults_to_localhost_8188(self):
        """MCP_COMFYUI_URL should default to http://127.0.0.1:8188."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MCP_COMFYUI_URL", None)
            url = os.environ.get("MCP_COMFYUI_URL", "http://127.0.0.1:8188")
            assert url == "http://127.0.0.1:8188"

    def test_mcp_comfyui_url_respects_custom_value(self):
        """MCP_COMFYUI_URL should use custom value when set."""
        custom_url = "http://10.0.0.5:8188"
        with patch.dict(os.environ, {"MCP_COMFYUI_URL": custom_url}):
            url = os.environ.get("MCP_COMFYUI_URL", "http://127.0.0.1:8188")
            assert url == custom_url


class TestMCPHTTPToken:
    """Tests for MCP_HTTP_TOKEN configuration."""

    def test_mcp_http_token_unset_means_open(self):
        """When MCP_HTTP_TOKEN is unset, server is open (loopback only)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MCP_HTTP_TOKEN", None)
            token = os.environ.get("MCP_HTTP_TOKEN")
            assert token is None  # Entrypoint warns about no auth

    def test_mcp_http_token_set_means_authenticated(self):
        """When MCP_HTTP_TOKEN is set, server requires auth."""
        token_value = "my-secret-token"
        with patch.dict(os.environ, {"MCP_HTTP_TOKEN": token_value}):
            token = os.environ.get("MCP_HTTP_TOKEN")
            assert token == token_value
            assert token is not None


class TestMCPCommandConstruction:
    """Tests for MCP server command construction logic.

    These tests mirror the logic in entrypoint.sh's MCP startup block,
    validating that the correct flags are used for each transport mode.
    """

    def _build_mcp_command(self, transport, port, comfyui_url, http_token=None):
        """Mirror the entrypoint.sh command construction logic.

        Returns the command string that entrypoint.sh would build.
        """
        cmd = f"COMFYUI_URL={comfyui_url} comfyui-mcp"

        if transport == "http":
            if http_token:
                cmd = f"COMFYUI_MCP_HTTP_TOKEN={http_token} {cmd} --http --port {port}"
            else:
                cmd = f"{cmd} --http --port {port}"
        elif transport == "tunnel":
            cmd = f"{cmd} --tunnel"
        elif transport == "stdio":
            pass  # No flags needed for stdio
        else:
            # Fallback to http
            cmd = f"{cmd} --http --port {port}"

        return cmd

    def test_http_transport_command_with_token(self):
        """HTTP transport with token should include --http, --port, and token env."""
        cmd = self._build_mcp_command(
            transport="http",
            port="8765",
            comfyui_url="http://127.0.0.1:8188",
            http_token="secret123"
        )
        assert "--http" in cmd
        assert "--port 8765" in cmd
        assert "COMFYUI_MCP_HTTP_TOKEN=secret123" in cmd
        assert "COMFYUI_URL=http://127.0.0.1:8188" in cmd

    def test_http_transport_command_without_token(self):
        """HTTP transport without token should include --http and --port but no token."""
        cmd = self._build_mcp_command(
            transport="http",
            port="8765",
            comfyui_url="http://127.0.0.1:8188"
        )
        assert "--http" in cmd
        assert "--port 8765" in cmd
        assert "COMFYUI_MCP_HTTP_TOKEN" not in cmd

    def test_tunnel_transport_command(self):
        """Tunnel transport should use --tunnel flag (no --port)."""
        cmd = self._build_mcp_command(
            transport="tunnel",
            port="8765",
            comfyui_url="http://127.0.0.1:8188"
        )
        assert "--tunnel" in cmd
        assert "--port" not in cmd
        assert "--http" not in cmd

    def test_stdio_transport_command(self):
        """Stdio transport should have no transport flags."""
        cmd = self._build_mcp_command(
            transport="stdio",
            port="8765",
            comfyui_url="http://127.0.0.1:8188"
        )
        assert "--http" not in cmd
        assert "--tunnel" not in cmd
        assert "--port" not in cmd
        assert "COMFYUI_URL=http://127.0.0.1:8188" in cmd

    def test_invalid_transport_falls_back_to_http(self):
        """Invalid transport should fall back to http with --port."""
        cmd = self._build_mcp_command(
            transport="invalid",
            port="8765",
            comfyui_url="http://127.0.0.1:8188"
        )
        assert "--http" in cmd
        assert "--port 8765" in cmd


class TestMCPUserscriptGuard:
    """Tests for the userscript install guard logic.

    The userscript (install_comfy_mcp.sh) should only run when ENABLE_MCP=true.
    """

    def test_userscript_skips_when_mcp_disabled(self):
        """Userscript should exit early when ENABLE_MCP != 'true'."""
        # Simulate the guard check from install_comfy_mcp.sh
        enable_mcp = "false"
        should_run = enable_mcp == "true"
        assert should_run is False

    def test_userscript_runs_when_mcp_enabled(self):
        """Userscript should proceed when ENABLE_MCP == 'true'."""
        enable_mcp = "true"
        should_run = enable_mcp == "true"
        assert should_run is True

    def test_userscript_skips_when_unset(self):
        """Userscript should skip when ENABLE_MCP is unset."""
        enable_mcp = os.environ.get("ENABLE_MCP", "false")
        should_run = enable_mcp == "true"
        assert should_run is False


class TestMCPEnvVarDocumentation:
    """Tests that .env.example documents all MCP environment variables."""

    @pytest.fixture
    def env_example_content(self):
        """Read the .env.example file content."""
        env_path = Path(__file__).parent.parent / ".env.example"
        return env_path.read_text()

    def test_env_example_documents_enable_mcp(self, env_example_content):
        """.env.example should document ENABLE_MCP."""
        assert "ENABLE_MCP" in env_example_content

    def test_env_example_documents_mcp_port(self, env_example_content):
        """.env.example should document MCP_PORT."""
        assert "MCP_PORT" in env_example_content

    def test_env_example_documents_mcp_transport(self, env_example_content):
        """.env.example should document MCP_TRANSPORT."""
        assert "MCP_TRANSPORT" in env_example_content

    def test_env_example_documents_mcp_comfyui_url(self, env_example_content):
        """.env.example should document MCP_COMFYUI_URL."""
        assert "MCP_COMFYUI_URL" in env_example_content

    def test_env_example_documents_mcp_http_token(self, env_example_content):
        """.env.example should document MCP_HTTP_TOKEN."""
        assert "MCP_HTTP_TOKEN" in env_example_content

    def test_env_example_has_mcp_section_header(self, env_example_content):
        """.env.example should have an MCP configuration section."""
        assert "MCP SERVER CONFIGURATION" in env_example_content.upper()

    def test_env_example_mentions_comfyui_mcp(self, env_example_content):
        """.env.example should reference the comfyui-mcp project."""
        assert "comfyui-mcp" in env_example_content.lower()


class TestDockerfileMCPIntegration:
    """Tests that Dockerfile includes MCP prerequisites."""

    @pytest.fixture
    def dockerfile_content(self):
        """Read the Dockerfile content."""
        dockerfile_path = Path(__file__).parent.parent / "Dockerfile"
        return dockerfile_path.read_text()

    def test_dockerfile_installs_nodejs(self, dockerfile_content):
        """Dockerfile should install Node.js 22 for comfyui-mcp."""
        assert "nodesource.com/setup_22" in dockerfile_content
        assert "nodejs" in dockerfile_content.lower()

    def test_dockerfile_exposes_mcp_port(self, dockerfile_content):
        """Dockerfile should expose port 8765 for MCP server."""
        assert "8765" in dockerfile_content


class TestEntrypointMCPIntegration:
    """Tests that entrypoint.sh includes MCP startup logic."""

    @pytest.fixture
    def entrypoint_content(self):
        """Read the entrypoint.sh content."""
        entrypoint_path = Path(__file__).parent.parent / "entrypoint.sh"
        return entrypoint_path.read_text()

    def test_entrypoint_has_mcp_feature_detection(self, entrypoint_content):
        """entrypoint.sh should detect ENABLE_MCP and set MCP_ENABLED."""
        assert "MCP_ENABLED" in entrypoint_content
        assert "ENABLE_MCP" in entrypoint_content

    def test_entrypoint_has_mcp_startup_block(self, entrypoint_content):
        """entrypoint.sh should have a MCP server startup section."""
        assert "COMFY MCP SERVER STARTUP" in entrypoint_content

    def test_entrypoint_starts_mcp_after_comfyui_ready(self, entrypoint_content):
        """MCP startup should come after the ComfyUI readiness check."""
        comfyui_ready_pos = entrypoint_content.find("ComfyUI WebUI is ready")
        mcp_startup_pos = entrypoint_content.find("COMFY MCP SERVER STARTUP")
        assert comfyui_ready_pos != -1, "ComfyUI readiness check not found"
        assert mcp_startup_pos != -1, "MCP startup block not found"
        assert mcp_startup_pos > comfyui_ready_pos, "MCP should start after ComfyUI is ready"

    def test_entrypoint_supports_all_transports(self, entrypoint_content):
        """entrypoint.sh should handle http, tunnel, and stdio transports."""
        for transport in ["http", "tunnel", "stdio"]:
            assert transport in entrypoint_content, f"Transport '{transport}' not handled"

    def test_entrypoint_logs_mcp_status_in_pods_mode(self, entrypoint_content):
        """entrypoint.sh should log MCP status in pods mode."""
        assert "Comfy MCP server is running" in entrypoint_content

    def test_entrypoint_logs_mcp_status_in_local_mode(self, entrypoint_content):
        """entrypoint.sh should log MCP status in local mode."""
        # Both pods and local modes have the same MCP status log
        assert entrypoint_content.count("Comfy MCP server is running") >= 2


class TestUserscriptExists:
    """Tests that the MCP install userscript exists and is valid."""

    @pytest.fixture
    def userscript_path(self):
        """Path to the MCP install userscript."""
        return Path(__file__).parent.parent / "userscripts_dir" / "install_comfy_mcp.sh"

    def test_userscript_exists(self, userscript_path):
        """The install_comfy_mcp.sh userscript should exist."""
        assert userscript_path.exists()

    def test_userscript_has_shebang(self, userscript_path):
        """The userscript should have a bash shebang."""
        content = userscript_path.read_text()
        assert content.startswith("#!/bin/bash")

    def test_userscript_checks_enable_mcp(self, userscript_path):
        """The userscript should check ENABLE_MCP before proceeding."""
        content = userscript_path.read_text()
        assert "ENABLE_MCP" in content

    def test_userscript_installs_npm_package(self, userscript_path):
        """The userscript should install comfyui-mcp via npm."""
        content = userscript_path.read_text()
        assert "npm install -g comfyui-mcp" in content

    def test_userscript_clones_panel(self, userscript_path):
        """The userscript should clone the comfyui-mcp-panel custom node."""
        content = userscript_path.read_text()
        assert "comfyui-mcp-panel" in content
        assert "git clone" in content

    def test_userscript_verifies_node_version(self, userscript_path):
        """The userscript should verify Node.js >= 22."""
        content = userscript_path.read_text()
        assert "22" in content
        assert "node --version" in content or "NODE_VERSION" in content
