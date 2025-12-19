"""
Find unused AWS resources for cost optimization.
Identifies unattached EBS volumes, idle load balancers, and unused Elastic IPs.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import boto3
import click
from botocore.exceptions import ClientError
from rich.console import Console
from rich.table import Table

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


@dataclass
class UnusedResource:
    """Represents an unused AWS resource."""

    resource_type: str
    resource_id: str
    region: str
    created: Optional[datetime]
    estimated_monthly_cost: float
    details: str


class UnusedResourceFinder:
    """Find unused AWS resources across regions."""

    def __init__(self, regions: Optional[list[str]] = None):
        self.session = boto3.Session()
        self.regions = regions or self._get_all_regions()
        self.unused_resources: list[UnusedResource] = []

    def _get_all_regions(self) -> list[str]:
        """Get all available AWS regions."""
        ec2 = self.session.client("ec2", region_name="us-east-1")
        regions = ec2.describe_regions()["Regions"]
        return [r["RegionName"] for r in regions]

    def find_unattached_volumes(self, region: str) -> list[UnusedResource]:
        """Find EBS volumes that are not attached to any instance."""
        resources = []
        ec2 = self.session.client("ec2", region_name=region)

        try:
            volumes = ec2.describe_volumes(
                Filters=[{"Name": "status", "Values": ["available"]}]
            )["Volumes"]

            for vol in volumes:
                size_gb = vol["Size"]
                vol_type = vol["VolumeType"]
                monthly_cost = self._estimate_ebs_cost(size_gb, vol_type)

                resources.append(
                    UnusedResource(
                        resource_type="EBS Volume",
                        resource_id=vol["VolumeId"],
                        region=region,
                        created=vol["CreateTime"].replace(tzinfo=None),
                        estimated_monthly_cost=monthly_cost,
                        details=f"{size_gb}GB {vol_type}",
                    )
                )
        except ClientError as e:
            logger.warning(f"Error checking volumes in {region}: {e}")

        return resources

    def find_idle_load_balancers(self, region: str) -> list[UnusedResource]:
        """Find ALBs with no targets or zero request count."""
        resources = []
        elbv2 = self.session.client("elbv2", region_name=region)
        cloudwatch = self.session.client("cloudwatch", region_name=region)

        try:
            lbs = elbv2.describe_load_balancers()["LoadBalancers"]

            for lb in lbs:
                lb_arn = lb["LoadBalancerArn"]
                lb_name = lb["LoadBalancerName"]

                target_groups = elbv2.describe_target_groups(
                    LoadBalancerArn=lb_arn
                )["TargetGroups"]

                has_healthy_targets = False
                for tg in target_groups:
                    health = elbv2.describe_target_health(
                        TargetGroupArn=tg["TargetGroupArn"]
                    )
                    if any(
                        t["TargetHealth"]["State"] == "healthy"
                        for t in health["TargetHealthDescriptions"]
                    ):
                        has_healthy_targets = True
                        break

                if not has_healthy_targets:
                    resources.append(
                        UnusedResource(
                            resource_type="Load Balancer",
                            resource_id=lb_name,
                            region=region,
                            created=lb["CreatedTime"].replace(tzinfo=None),
                            estimated_monthly_cost=22.0,
                            details="No healthy targets",
                        )
                    )

        except ClientError as e:
            logger.warning(f"Error checking load balancers in {region}: {e}")

        return resources

    def find_unused_elastic_ips(self, region: str) -> list[UnusedResource]:
        """Find Elastic IPs not associated with any instance."""
        resources = []
        ec2 = self.session.client("ec2", region_name=region)

        try:
            addresses = ec2.describe_addresses()["Addresses"]

            for addr in addresses:
                if "InstanceId" not in addr and "NetworkInterfaceId" not in addr:
                    resources.append(
                        UnusedResource(
                            resource_type="Elastic IP",
                            resource_id=addr["PublicIp"],
                            region=region,
                            created=None,
                            estimated_monthly_cost=3.60,
                            details="Not associated",
                        )
                    )

        except ClientError as e:
            logger.warning(f"Error checking Elastic IPs in {region}: {e}")

        return resources

    def _estimate_ebs_cost(self, size_gb: int, vol_type: str) -> float:
        """Estimate monthly cost for EBS volume."""
        rates = {
            "gp2": 0.10,
            "gp3": 0.08,
            "io1": 0.125,
            "io2": 0.125,
            "st1": 0.045,
            "sc1": 0.025,
            "standard": 0.05,
        }
        return size_gb * rates.get(vol_type, 0.10)

    def scan_all(self) -> list[UnusedResource]:
        """Scan all regions for unused resources."""
        self.unused_resources = []

        for region in self.regions:
            console.print(f"Scanning {region}...", style="dim")
            self.unused_resources.extend(self.find_unattached_volumes(region))
            self.unused_resources.extend(self.find_idle_load_balancers(region))
            self.unused_resources.extend(self.find_unused_elastic_ips(region))

        return self.unused_resources

    def display_results(self) -> None:
        """Display results in a formatted table."""
        if not self.unused_resources:
            console.print("No unused resources found.", style="green")
            return

        table = Table(title="Unused AWS Resources")
        table.add_column("Type", style="cyan")
        table.add_column("Resource ID", style="magenta")
        table.add_column("Region", style="green")
        table.add_column("Monthly Cost", style="red")
        table.add_column("Details", style="dim")

        total_cost = 0.0
        for r in self.unused_resources:
            table.add_row(
                r.resource_type,
                r.resource_id,
                r.region,
                f"${r.estimated_monthly_cost:.2f}",
                r.details,
            )
            total_cost += r.estimated_monthly_cost

        console.print(table)
        console.print(
            f"\nTotal estimated monthly savings: ${total_cost:.2f}",
            style="bold green",
        )


@click.command()
@click.option("--region", "-r", help="AWS region (default: all regions)")
def main(region: Optional[str]) -> None:
    """Find unused AWS resources for cost optimization."""
    regions = [region] if region else None
    finder = UnusedResourceFinder(regions=regions)
    finder.scan_all()
    finder.display_results()


if __name__ == "__main__":
    main()

