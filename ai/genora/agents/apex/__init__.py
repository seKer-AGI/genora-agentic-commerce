"""GenOra Apex — enterprise agent.

STATUS: **PLANNED / NOT IMPLEMENTED.**

This module only defines the architecture and extension points Apex will build on. Nothing here
performs enterprise actions, and :func:`build_apex` refuses to construct an agent. See docs/genora-apex.md.

Planned capabilities
--------------------
* Multi-organization tenancy with organization-scoped permissions (``OrganizationContext``)
* Enterprise tools from external business systems (ERP, CRM, WMS) exposed through an
  MCP-compatible tool bridge (``EnterpriseToolProvider`` / ``MCPToolDescriptor``)
* Long-running, multi-step automations with human approval gates (``ApprovalPolicy``)
* Immutable, exportable audit trails (``AuditSink``)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

APEX_STATUS: Literal["planned"] = "planned"
APEX_STATUS_LABEL = "Planned / Not Implemented"

PLANNED_CAPABILITIES = [
    "Organization-level workspaces, roles and permissions",
    "Connectors to external business systems (ERP, CRM, inventory, accounting)",
    "MCP-compatible enterprise tool registry",
    "Multi-step automations with approval workflows",
    "Organization-wide audit logs and compliance exports",
    "Advanced analytics and scheduled reporting",
]


@dataclass(frozen=True)
class OrganizationContext:
    """Identity of an enterprise tenant; will scope every Apex tool call."""

    organization_id: uuid.UUID
    user_id: uuid.UUID
    org_roles: frozenset[str]
    org_permissions: frozenset[str]
    data_region: str | None = None


@dataclass
class MCPToolDescriptor:
    """Mirror of a Model Context Protocol tool definition (name, description, JSON input schema)."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server: str
    requires_approval: bool = True


class EnterpriseToolProvider(ABC):
    """Bridge that exposes tools from an external system (e.g. an MCP server) to Apex."""

    @abstractmethod
    def list_tools(self, org: OrganizationContext) -> list[MCPToolDescriptor]: ...

    @abstractmethod
    def call(self, org: OrganizationContext, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class ApprovalPolicy:
    """Which actions need which approvers before an automation step may run."""

    tool_pattern: str
    approver_roles: list[str] = field(default_factory=list)
    min_approvals: int = 1


class AuditSink(Protocol):
    def write(self, org: OrganizationContext, event: str, payload: dict[str, Any]) -> None: ...


class ApexNotImplementedError(NotImplementedError):
    pass


def build_apex(*_: Any, **__: Any) -> Any:
    raise ApexNotImplementedError("GenOra Apex is planned and not implemented yet")


def describe() -> dict[str, Any]:
    return {"agent": "apex", "display_name": "GenOra Apex", "status": APEX_STATUS, "label": APEX_STATUS_LABEL,
            "planned_capabilities": PLANNED_CAPABILITIES}
