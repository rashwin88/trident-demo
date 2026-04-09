"""Fake operational tools for the Task Agent demo.

These tools simulate real infrastructure operations (AWS, SSH, Slack,
PagerDuty, DNS, health checks) so the Task Agent can demonstrate
SOP execution end-to-end without touching actual systems.

Each tool uses asyncio.sleep to simulate realistic latency, making the
streaming demo feel authentic.  Results are plausible but obviously fake.

The TASK_TOOLS list is bound to the Task Agent's LLM alongside the
Trident READ_TOOLS, giving it both knowledge-graph access and
operational capability.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def aws_rds_status(
    instance_id: Annotated[str, "RDS instance identifier, e.g. 'prod-aurora-pg-01'"],
) -> str:
    """Check the current status of an AWS RDS instance. Returns status, endpoint,
    engine, availability zone, and recent events."""
    await asyncio.sleep(1.2)
    # Simulate different statuses based on instance name
    if "writer" in instance_id or "primary" in instance_id:
        status = "unavailable"
        events = ["Health check failed (3 consecutive)", "Automated monitoring triggered"]
    elif "reader" in instance_id or "standby" in instance_id:
        status = "available"
        events = ["Replication lag: 0.2s", "Last backup: 2 hours ago"]
    else:
        status = "available"
        events = ["Running normally"]

    return json.dumps({
        "instance_id": instance_id,
        "status": status,
        "engine": "aurora-postgresql 15.4",
        "endpoint": f"{instance_id}.cluster-xyz.us-east-1.rds.amazonaws.com",
        "az": "us-east-1a",
        "multi_az": True,
        "recent_events": events,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


@tool
async def aws_rds_failover(
    cluster_id: Annotated[str, "RDS cluster identifier to fail over"],
    target_instance: Annotated[str, "Target reader instance to promote"] = "",
) -> str:
    """Initiate a manual failover of an RDS Aurora cluster. Promotes the target
    reader to become the new writer. Takes 30-120 seconds in practice."""
    await asyncio.sleep(2.0)
    target = target_instance or f"{cluster_id}-reader-1"
    return json.dumps({
        "action": "failover-initiated",
        "cluster_id": cluster_id,
        "promoted_instance": target,
        "event_id": f"rds-event-{int(datetime.now(timezone.utc).timestamp())}",
        "estimated_seconds": 60,
        "message": f"Failover in progress. Promoting {target} to writer role.",
    })


@tool
async def ssh_run_command(
    host: Annotated[str, "Hostname or IP to SSH into"],
    command: Annotated[str, "Shell command to execute"],
    username: str = "ops",
) -> str:
    """SSH into a remote host and execute a command. Returns stdout, stderr,
    and exit code. Use for health checks, diagnostics, and verification."""
    await asyncio.sleep(1.5)

    # Simulate responses for common commands
    if "health" in command.lower() or "check" in command.lower():
        stdout = "Health check passed: all 12 critical tables accessible\nReplication lag: 0.3s\nConnections: 42/50 active"
        exit_code = 0
    elif "psql" in command.lower() or "select" in command.lower():
        stdout = " ?column?\n----------\n        1\n(1 row)\n\nConnection OK — latency 2.3ms"
        exit_code = 0
    elif "ping" in command.lower():
        stdout = "PING target: 3 packets transmitted, 3 received, 0% packet loss\nrtt avg = 1.2ms"
        exit_code = 0
    elif "systemctl" in command.lower():
        stdout = "● service active (running) since 2024-03-15 08:00:00 UTC\n  Memory: 256M\n  CPU: 2.1%"
        exit_code = 0
    elif "verify" in command.lower() or "checksum" in command.lower():
        stdout = "Verifying 12 critical tables...\n  users: OK (CRC32 match)\n  transactions: OK\n  accounts: OK\n  ledger: OK\n  audit_log: OK\n  sessions: OK\n  api_keys: OK\n  webhooks: OK\n  notifications: OK\n  rate_limits: OK\n  feature_flags: OK\n  tenant_config: OK\nAll checksums match. Data integrity verified."
        exit_code = 0
    else:
        stdout = f"Command executed: {command}"
        exit_code = 0

    return json.dumps({
        "host": host,
        "username": username,
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": "",
    })


@tool
async def run_health_check(
    service_name: Annotated[str, "Name of the service to check"],
    endpoint: Annotated[str, "Health check endpoint URL"] = "",
) -> str:
    """Run a health check against a service. Returns overall status, individual
    check results, and response time."""
    await asyncio.sleep(1.0)
    return json.dumps({
        "service": service_name,
        "endpoint": endpoint or f"https://{service_name}.prod.internal/health",
        "status": "healthy",
        "response_time_ms": 23,
        "checks": {
            "database": "pass",
            "cache": "pass",
            "queue": "pass",
            "disk_space": "pass",
        },
        "version": "2.14.3",
        "uptime_hours": 720,
    })


@tool
async def slack_post_message(
    channel: Annotated[str, "Slack channel name, e.g. '#incident-response'"],
    message: Annotated[str, "Message text to post"],
) -> str:
    """Post a message to a Slack channel. Used for incident notifications,
    status updates, and resolution announcements."""
    await asyncio.sleep(0.8)
    return json.dumps({
        "ok": True,
        "channel": channel,
        "message_preview": message[:100] + ("..." if len(message) > 100 else ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_id": f"msg-{int(datetime.now(timezone.utc).timestamp())}",
    })


@tool
async def pagerduty_update_incident(
    incident_id: Annotated[str, "PagerDuty incident ID"],
    status: Annotated[str, "New status: 'acknowledged' or 'resolved'"],
    note: str = "",
) -> str:
    """Update a PagerDuty incident status. Acknowledge when starting work,
    resolve when the issue is fixed."""
    await asyncio.sleep(0.6)
    return json.dumps({
        "incident_id": incident_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "note": note or f"Incident {status} by Task Agent",
        "severity": "P1",
        "service": "Production Database",
    })


@tool
async def dns_update_record(
    domain: Annotated[str, "Domain name to update, e.g. 'db-write.prod.internal'"],
    record_type: Annotated[str, "DNS record type: A, CNAME, etc."],
    value: Annotated[str, "New record value (IP or hostname)"],
    ttl: int = 300,
) -> str:
    """Update a DNS record. Used for failover scenarios where endpoints need
    to be redirected to new instances."""
    await asyncio.sleep(1.0)
    return json.dumps({
        "domain": domain,
        "record_type": record_type,
        "old_value": "10.0.1.100",
        "new_value": value,
        "ttl": ttl,
        "propagation_estimate_seconds": ttl,
        "status": "propagating",
        "message": f"DNS record updated. Full propagation in ~{ttl}s.",
    })


# All task-specific tools exported as a list
TASK_TOOLS = [
    aws_rds_status,
    aws_rds_failover,
    ssh_run_command,
    run_health_check,
    slack_post_message,
    pagerduty_update_incident,
    dns_update_record,
]
