# DevOps Python Tools

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Collection of Python utilities for DevOps automation, infrastructure management, and operational tasks.

## Tools

| Module | Description |
|--------|-------------|
| aws/ | AWS resource management, cost analysis |
| kubernetes/ | K8s cluster operations, pod health |
| docker/ | Image cleanup, container management |
| monitoring/ | Metrics collection, alerting |
| security/ | Secret rotation, vulnerability scanning |
| utils/ | Common utilities and helpers |

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### AWS Tools

```bash
# List unused resources
python -m aws.unused_resources --region us-east-1

# Cost analysis
python -m aws.cost_analyzer --days 30
```

### Kubernetes Tools

```bash
# Check pod health
python -m kubernetes.pod_health --namespace production

# Clean up failed pods
python -m kubernetes.cleanup --dry-run
```

### Docker Tools

```bash
# Clean old images
python -m docker.image_cleanup --days 30
```

## Testing

```bash
pytest tests/ -v --cov=.
```

## Author

Ashwath Abraham Stephen
Senior DevOps Engineer | [LinkedIn](https://linkedin.com/in/ashwathstephen) | [GitHub](https://github.com/ashwathstephen)

## License

MIT License - see [LICENSE](LICENSE) for details.

