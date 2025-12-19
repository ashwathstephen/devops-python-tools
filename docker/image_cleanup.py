"""
Docker image cleanup utility.
Removes dangling images, old tagged images, and unused containers.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import click
import docker
from docker.errors import APIError
from rich.console import Console
from rich.table import Table

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ImageInfo:
    """Docker image information."""

    image_id: str
    tags: list[str]
    size_mb: float
    created: datetime
    age_days: float


class DockerImageCleaner:
    """Clean up Docker images."""

    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise

    def list_images(
        self,
        min_age_days: int = 0,
        include_dangling: bool = True,
    ) -> list[ImageInfo]:
        """List all images with their information."""
        images_info = []

        try:
            images = self.client.images.list(all=include_dangling)
        except APIError as e:
            logger.error(f"Failed to list images: {e}")
            return images_info

        for img in images:
            created_str = img.attrs.get("Created", "")
            if created_str:
                created = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00")
                )
            else:
                created = datetime.now(timezone.utc)

            age = datetime.now(timezone.utc) - created
            age_days = age.total_seconds() / 86400

            if age_days < min_age_days:
                continue

            size_mb = img.attrs.get("Size", 0) / (1024 * 1024)
            tags = img.tags if img.tags else ["<none>:<none>"]

            images_info.append(
                ImageInfo(
                    image_id=img.short_id.replace("sha256:", ""),
                    tags=tags,
                    size_mb=size_mb,
                    created=created,
                    age_days=age_days,
                )
            )

        return sorted(images_info, key=lambda x: x.age_days, reverse=True)

    def get_dangling_images(self) -> list[ImageInfo]:
        """Get dangling (untagged) images."""
        all_images = self.list_images()
        return [img for img in all_images if img.tags == ["<none>:<none>"]]

    def cleanup_dangling(self, dry_run: bool = True) -> tuple[int, float]:
        """Remove dangling images."""
        dangling = self.get_dangling_images()
        removed_count = 0
        freed_mb = 0.0

        for img in dangling:
            if dry_run:
                console.print(
                    f"[DRY RUN] Would remove: {img.image_id} ({img.size_mb:.1f}MB)"
                )
            else:
                try:
                    self.client.images.remove(img.image_id, force=True)
                    console.print(f"Removed: {img.image_id}")
                    removed_count += 1
                    freed_mb += img.size_mb
                except APIError as e:
                    logger.warning(f"Failed to remove {img.image_id}: {e}")

        return removed_count, freed_mb

    def cleanup_old_images(
        self,
        min_age_days: int = 30,
        keep_tags: Optional[list[str]] = None,
        dry_run: bool = True,
    ) -> tuple[int, float]:
        """Remove images older than specified days."""
        old_images = self.list_images(min_age_days=min_age_days)
        keep_tags = keep_tags or ["latest", "stable", "production"]
        removed_count = 0
        freed_mb = 0.0

        for img in old_images:
            should_keep = any(
                any(keep in tag for keep in keep_tags) for tag in img.tags
            )

            if should_keep:
                continue

            if dry_run:
                console.print(
                    f"[DRY RUN] Would remove: {img.tags[0]} "
                    f"({img.size_mb:.1f}MB, {img.age_days:.0f} days old)"
                )
            else:
                try:
                    self.client.images.remove(img.image_id, force=True)
                    console.print(f"Removed: {img.tags[0]}")
                    removed_count += 1
                    freed_mb += img.size_mb
                except APIError as e:
                    logger.warning(f"Failed to remove {img.tags[0]}: {e}")

        return removed_count, freed_mb

    def prune_system(self, dry_run: bool = True) -> dict:
        """Prune unused Docker objects."""
        if dry_run:
            console.print("[DRY RUN] Would prune: containers, images, networks, volumes")
            return {}

        try:
            result = {
                "containers": self.client.containers.prune(),
                "images": self.client.images.prune(),
                "networks": self.client.networks.prune(),
                "volumes": self.client.volumes.prune(),
            }
            return result
        except APIError as e:
            logger.error(f"Prune failed: {e}")
            return {}

    def display_images(self, images: list[ImageInfo]) -> None:
        """Display images in a table."""
        table = Table(title="Docker Images")
        table.add_column("Image ID", style="cyan")
        table.add_column("Tags", style="magenta")
        table.add_column("Size", style="green")
        table.add_column("Age (days)", style="yellow")

        total_size = 0.0
        for img in images:
            table.add_row(
                img.image_id,
                "\n".join(img.tags[:2]),
                f"{img.size_mb:.1f}MB",
                f"{img.age_days:.0f}",
            )
            total_size += img.size_mb

        console.print(table)
        console.print(f"\nTotal: {len(images)} images, {total_size / 1024:.2f}GB")


@click.command()
@click.option("--days", "-d", default=30, help="Remove images older than N days")
@click.option("--dangling", is_flag=True, help="Only remove dangling images")
@click.option("--dry-run", is_flag=True, default=True, help="Show what would be removed")
@click.option("--force", is_flag=True, help="Actually remove images")
def main(days: int, dangling: bool, dry_run: bool, force: bool) -> None:
    """Clean up Docker images."""
    if force:
        dry_run = False

    cleaner = DockerImageCleaner()

    if dangling:
        images = cleaner.get_dangling_images()
        cleaner.display_images(images)
        count, freed = cleaner.cleanup_dangling(dry_run=dry_run)
    else:
        images = cleaner.list_images(min_age_days=days)
        cleaner.display_images(images)
        count, freed = cleaner.cleanup_old_images(min_age_days=days, dry_run=dry_run)

    if not dry_run:
        console.print(
            f"\nRemoved {count} images, freed {freed / 1024:.2f}GB",
            style="bold green",
        )


if __name__ == "__main__":
    main()

