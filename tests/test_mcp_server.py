"""Tests for MCP server model caching integration."""

from __future__ import annotations

import pytest


class TestMCPLifespan:
    """Tests for MCP server lifespan hooks."""

    def test_lifespan_warm_load_env_var(self, mocker, monkeypatch):
        """Test that SCHOLARDOC_WARM_LOAD=true triggers model loading."""
        monkeypatch.setenv("SCHOLARDOC_WARM_LOAD", "true")

        # Mock ModelCache at the source module
        mock_cache = mocker.MagicMock()
        mock_cache_class = mocker.MagicMock(return_value=mock_cache)
        mock_cache_class.get_instance = mocker.MagicMock(return_value=mock_cache)
        mocker.patch.dict(
            "sys.modules",
            {"scholardoc_ocr.model_cache": mocker.MagicMock(ModelCache=mock_cache_class)},
        )

        # Import after mocking
        import importlib

        import scholardoc_ocr.mcp_server

        importlib.reload(scholardoc_ocr.mcp_server)
        # Run lifespan
        import asyncio

        from scholardoc_ocr.mcp_server import mcp_lifespan

        async def run_lifespan():
            async with mcp_lifespan(None):
                pass

        asyncio.run(run_lifespan())

        # Verify warm load happened
        mock_cache.get_models.assert_called_once()
        mock_cache.evict.assert_called_once()  # Cleanup on exit

    def test_lifespan_no_warm_load_by_default(self, mocker, monkeypatch):
        """Test that warm load is skipped by default."""
        monkeypatch.delenv("SCHOLARDOC_WARM_LOAD", raising=False)

        # Mock ModelCache at the source module
        mock_cache = mocker.MagicMock()
        mock_cache_class = mocker.MagicMock(return_value=mock_cache)
        mock_cache_class.get_instance = mocker.MagicMock(return_value=mock_cache)
        mocker.patch.dict(
            "sys.modules",
            {"scholardoc_ocr.model_cache": mocker.MagicMock(ModelCache=mock_cache_class)},
        )

        import importlib

        import scholardoc_ocr.mcp_server

        importlib.reload(scholardoc_ocr.mcp_server)
        import asyncio

        from scholardoc_ocr.mcp_server import mcp_lifespan

        async def run_lifespan():
            async with mcp_lifespan(None):
                pass

        asyncio.run(run_lifespan())

        # get_models NOT called during startup (only evict on cleanup)
        mock_cache.get_models.assert_not_called()
        mock_cache.evict.assert_called_once()


class TestOCRMemoryStats:
    """Tests for ocr_memory_stats tool."""

    @pytest.mark.asyncio
    async def test_ocr_memory_stats_returns_expected_keys(self, mocker):
        """Test that ocr_memory_stats returns correct structure."""
        # Mock ModelCache at the source module
        mock_cache = mocker.MagicMock()
        mock_cache.is_loaded.return_value = False
        mock_cache._ttl = 1800.0
        mock_cache_class = mocker.MagicMock()
        mock_cache_class.get_instance = mocker.MagicMock(return_value=mock_cache)

        mock_memory_stats = mocker.MagicMock(
            return_value={"device": "cpu", "allocated_mb": 0, "reserved_mb": 0}
        )

        mocker.patch.dict(
            "sys.modules",
            {
                "scholardoc_ocr.model_cache": mocker.MagicMock(
                    ModelCache=mock_cache_class, get_memory_stats=mock_memory_stats
                )
            },
        )

        import importlib

        import scholardoc_ocr.mcp_server

        importlib.reload(scholardoc_ocr.mcp_server)
        from scholardoc_ocr.mcp_server import ocr_memory_stats

        result = await ocr_memory_stats()

        assert "models_loaded" in result
        assert "device" in result
        assert "allocated_mb" in result
        assert "reserved_mb" in result
        assert "cache_ttl_seconds" in result
        assert result["models_loaded"] is False
        assert result["cache_ttl_seconds"] == 1800.0

    @pytest.mark.asyncio
    async def test_ocr_memory_stats_with_loaded_models(self, mocker):
        """Test ocr_memory_stats when models are loaded."""
        mock_cache = mocker.MagicMock()
        mock_cache.is_loaded.return_value = True
        mock_cache._ttl = 3600.0
        mock_cache_class = mocker.MagicMock()
        mock_cache_class.get_instance = mocker.MagicMock(return_value=mock_cache)

        mock_memory_stats = mocker.MagicMock(
            return_value={"device": "mps", "allocated_mb": 512.5, "reserved_mb": 0}
        )

        mocker.patch.dict(
            "sys.modules",
            {
                "scholardoc_ocr.model_cache": mocker.MagicMock(
                    ModelCache=mock_cache_class, get_memory_stats=mock_memory_stats
                )
            },
        )

        import importlib

        import scholardoc_ocr.mcp_server

        importlib.reload(scholardoc_ocr.mcp_server)
        from scholardoc_ocr.mcp_server import ocr_memory_stats

        result = await ocr_memory_stats()

        assert result["models_loaded"] is True
        assert result["device"] == "mps"
        assert result["allocated_mb"] == 512.5
