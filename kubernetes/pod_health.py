"""
Kubernetes pod health checker and analyzer.
Identifies unhealthy pods, resource issues, and restart patterns.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import click
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from rich.console import Console
from rich.table import Table

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


@dataclass
class PodHealthInfo:
    """Pod health information."""

    name: str
    namespace: str
    status: str
    restarts: int
    age_hours: float
    cpu_request: str
    memory_request: str
    issues: list[str]


class PodHealthChecker:
    """Check health of Kubernetes pods."""

    def __init__(self, kubeconfig: Optional[str] = None):
        try:
            if kubeconfig:
                config.load_kube_config(config_file=kubeconfig)
            else:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()
        except Exception as e:
            logger.error(f"Failed to load kubeconfig: {e}")
            raise

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def get_pod_health(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> list[PodHealthInfo]:
        """Get health information for pods."""
        pods_info = []

        try:
            if namespace:
                pods = self.v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector,
                )
            else:
                pods = self.v1.list_pod_for_all_namespaces(
                    label_selector=label_selector,
                )
        except ApiException as e:
            logger.error(f"Failed to list pods: {e}")
            return pods_info

        for pod in pods.items:
            issues = self._analyze_pod(pod)
            restarts = sum(
                cs.restart_count
                for cs in (pod.status.container_statuses or [])
            )

            age_hours = 0.0
            if pod.status.start_time:
                age = datetime.now(timezone.utc) - pod.status.start_time
                age_hours = age.total_seconds() / 3600

            cpu_req = "N/A"
            mem_req = "N/A"
            if pod.spec.containers:
                resources = pod.spec.containers[0].resources
                if resources and resources.requests:
                    cpu_req = resources.requests.get("cpu", "N/A")
                    mem_req = resources.requests.get("memory", "N/A")

            pods_info.append(
                PodHealthInfo(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace,
                    status=pod.status.phase,
                    restarts=restarts,
                    age_hours=age_hours,
                    cpu_request=cpu_req,
                    memory_request=mem_req,
                    issues=issues,
                )
            )

        return pods_info

    def _analyze_pod(self, pod) -> list[str]:
        """Analyze pod for potential issues."""
        issues = []

        if pod.status.phase in ("Failed", "Unknown"):
            issues.append(f"Pod in {pod.status.phase} state")

        for cs in pod.status.container_statuses or []:
            if cs.restart_count > 5:
                issues.append(f"High restart count: {cs.restart_count}")

            if cs.state.waiting:
                reason = cs.state.waiting.reason
                if reason in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
                    issues.append(f"Container waiting: {reason}")

            if cs.state.terminated:
                if cs.state.terminated.exit_code != 0:
                    issues.append(
                        f"Container exited with code {cs.state.terminated.exit_code}"
                    )

        for cond in pod.status.conditions or []:
            if cond.type == "Ready" and cond.status != "True":
                issues.append(f"Not ready: {cond.reason}")
            if cond.type == "PodScheduled" and cond.status != "True":
                issues.append(f"Scheduling issue: {cond.reason}")

        return issues

    def get_unhealthy_pods(
        self,
        namespace: Optional[str] = None,
    ) -> list[PodHealthInfo]:
        """Get only unhealthy pods."""
        all_pods = self.get_pod_health(namespace=namespace)
        return [p for p in all_pods if p.issues or p.status != "Running"]

    def display_health_report(
        self,
        pods: list[PodHealthInfo],
        show_healthy: bool = False,
    ) -> None:
        """Display pod health in a table."""
        if show_healthy:
            display_pods = pods
        else:
            display_pods = [p for p in pods if p.issues or p.status != "Running"]

        if not display_pods:
            console.print("All pods are healthy.", style="green")
            return

        table = Table(title="Pod Health Report")
        table.add_column("Namespace", style="cyan")
        table.add_column("Pod", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Restarts", style="yellow")
        table.add_column("Age (h)", style="dim")
        table.add_column("Issues", style="red")

        for pod in display_pods:
            status_style = "green" if pod.status == "Running" else "red"
            issues_str = "; ".join(pod.issues) if pod.issues else "-"

            table.add_row(
                pod.namespace,
                pod.name[:40],
                f"[{status_style}]{pod.status}[/{status_style}]",
                str(pod.restarts),
                f"{pod.age_hours:.1f}",
                issues_str,
            )

        console.print(table)

        healthy = len([p for p in pods if not p.issues and p.status == "Running"])
        unhealthy = len(pods) - healthy
        console.print(
            f"\nTotal: {len(pods)} pods | Healthy: {healthy} | Issues: {unhealthy}"
        )


@click.command()
@click.option("--namespace", "-n", help="Kubernetes namespace")
@click.option("--all", "show_all", is_flag=True, help="Show all pods including healthy")
@click.option("--kubeconfig", "-k", help="Path to kubeconfig file")
def main(namespace: Optional[str], show_all: bool, kubeconfig: Optional[str]) -> None:
    """Check Kubernetes pod health."""
    checker = PodHealthChecker(kubeconfig=kubeconfig)
    pods = checker.get_pod_health(namespace=namespace)
    checker.display_health_report(pods, show_healthy=show_all)


if __name__ == "__main__":
    main()

