"""Tests for Docker image cleanup utility."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from docker.image_cleanup import DockerImageCleaner, ImageInfo


class TestImageInfo:
    """Tests for ImageInfo dataclass."""

    def test_image_info_creation(self):
        """Test creating an ImageInfo instance."""
        info = ImageInfo(
            image_id="abc123",
            tags=["myapp:latest"],
            size_mb=150.5,
            created=datetime.now(timezone.utc),
            age_days=5.0,
        )

        assert info.image_id == "abc123"
        assert "myapp:latest" in info.tags
        assert info.size_mb == 150.5
        assert info.age_days == 5.0


class TestDockerImageCleaner:
    """Tests for DockerImageCleaner class."""

    @patch("docker.image_cleanup.docker")
    def test_cleaner_initialization(self, mock_docker):
        """Test cleaner initializes with Docker client."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        cleaner = DockerImageCleaner()

        mock_docker.from_env.assert_called_once()
        mock_client.ping.assert_called_once()

    @patch("docker.image_cleanup.docker")
    def test_get_dangling_images(self, mock_docker):
        """Test filtering dangling images."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        mock_image = MagicMock()
        mock_image.short_id = "sha256:abc123"
        mock_image.tags = []
        mock_image.attrs = {
            "Created": "2025-01-01T00:00:00Z",
            "Size": 100 * 1024 * 1024,
        }
        mock_client.images.list.return_value = [mock_image]

        cleaner = DockerImageCleaner()
        dangling = cleaner.get_dangling_images()

        assert len(dangling) == 1
        assert dangling[0].tags == ["<none>:<none>"]

    @patch("docker.image_cleanup.docker")
    def test_cleanup_dry_run(self, mock_docker):
        """Test cleanup in dry run mode."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client

        mock_image = MagicMock()
        mock_image.short_id = "sha256:abc123"
        mock_image.tags = []
        mock_image.attrs = {
            "Created": "2025-01-01T00:00:00Z",
            "Size": 100 * 1024 * 1024,
        }
        mock_client.images.list.return_value = [mock_image]

        cleaner = DockerImageCleaner()
        count, freed = cleaner.cleanup_dangling(dry_run=True)

        assert count == 0
        assert freed == 0.0
        mock_client.images.remove.assert_not_called()

