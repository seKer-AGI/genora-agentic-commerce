"""GenOra runtime: binds the AI engine to the marketplace (identity, persistence, audit, memory)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Any

from genora.agents import apex
from genora.agents.astra import build_astra
from genora.agents.nova import build_nova
from genora.core.engine import GenOraEngine, TurnOutcome
from genora.core.memory import SessionState
from genora.core.tools import ToolCallRecord, ToolContext, ToolExecutor, ToolRegistry
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.agents.astra_tools import ASTRA_TOOL_IMPLEMENTATIONS
from app.agents.base import AgentServices
from app.agents.nova_tools import NOVA_TOOL_IMPLEMENTATIONS
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, NotImplementedFeature, PermissionDenied, ServiceUnavailable
from app.core.logging import log_event
from app.core.principal import Principal
from app.core.rbac import P
from app.core.security import utcnow
from app.models.agents import AgentSession, AgentToolCall, AgentWorkflow, Conversation, Message
from app.models.analytics import AnalyticsEvent
from app.models.catalog import Category, Product
from app.models.enums import AgentName, MessageRole, ProductStatus, ToolCallStatus, WorkflowStatus
from app.models.identity import SystemSetting
from app.services.ai_runtime import describe_ai_runtime, get_llm_provider

logger = logging.getLogger("app.agents")

AGENT_PERMISSIONS = {"nova": P.NOVA_USE, "astra": P.ASTRA_USE}
SESSION_TTL = timedelta(days=7)


@lru_cache
def tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for tool in [*NOVA_TOOL_IMPLEMENTATIONS, *ASTRA_TOOL_IMPLEMENTATIONS]:
        reg.register(tool)
    return reg


@lru_cache(maxsize=4)
def engine_for(agent: str, use_llm: bool) -> GenOraEngine:
    llm = get_llm_provider() if use_llm else None
    definition = build_nova(llm) if agent == "nova" else build_astra(llm)
    return GenOraEngine(definition, llm, use_llm_phrasing=use_llm)


class DbToolRecorder:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(self, ctx: ToolContext, record: ToolCallRecord) -> None:
        if ctx.workflow_id is None:
            return
        self.db.add(AgentToolCall(workflow_id=ctx.workflow_id, tool_name=record.tool, status=ToolCallStatus(record.status),
                                  input=record.input, output_summary=record.output_summary, error_code=record.error_code,
                                  latency_ms=record.latency_ms))
        self.db.flush()


@dataclass
class Attachment:
    data: bytes
    mime: str
    name: str


class AgentRuntime:
    def __init__(self, db: Session, principal: Principal) -> None:
        self.db = db
        self.principal = principal
        self.settings = get_settings()

    # ------------------------------------------------------------ settings / access
    def _setting(self, key: str, default: Any) -> Any:
        row = self.db.get(SystemSetting, key)
        return row.value if row is not None else default

    def authorize(self, agent: str) -> None:
        if agent == "apex":
            raise NotImplementedFeature("GenOra Apex is planned and not implemented yet", code="APEX_NOT_IMPLEMENTED")
        if agent not in AGENT_PERMISSIONS:
            raise NotFoundError("Unknown agent", code="AGENT_NOT_FOUND")
        if not self._setting(f"agents.{agent}.enabled", True):
            raise ServiceUnavailable(f"GenOra {agent.capitalize()} is currently disabled", code="AGENT_DISABLED")
        if not self.principal.has(AGENT_PERMISSIONS[agent]):
            raise PermissionDenied(f"Your account cannot use GenOra {agent.capitalize()}", code="AGENT_FORBIDDEN")
        if agent == "astra" and self.principal.seller_id is None:
            raise PermissionDenied("GenOra Astra requires an active seller profile", code="SELLER_REQUIRED")

    def status(self) -> dict[str, Any]:
        runtime = describe_ai_runtime()
        agents = []
        for name, display in (("nova", "GenOra Nova"), ("astra", "GenOra Astra")):
            defn = engine_for(name, False).agent
            allowed = True
            try:
                self.authorize(name)
            except Exception:  # noqa: BLE001 - status is informational
                allowed = False
            agents.append({"agent": name, "display_name": display, "status": "available",
                           "enabled": bool(self._setting(f"agents.{name}.enabled", True)), "can_use": allowed,
                           "capabilities": defn.capabilities, "intents": defn.intents,
                           "tools": [t.describe() for t in tool_registry().for_agent(name)]})
        agents.append({**apex.describe(), "enabled": False, "can_use": False, "status": "planned"})
        return {"agents": agents, "runtime": runtime}

    # ------------------------------------------------------------ conversations
    def create_conversation(self, agent: str, title: str | None = None) -> Conversation:
        self.authorize(agent)
        conv = Conversation(user_id=self.principal.user_id, agent=AgentName(agent), title=title)
        self.db.add(conv)
        self.db.flush()
        self.db.add(AgentSession(conversation_id=conv.id, user_id=self.principal.user_id, agent=AgentName(agent),
                                 context={}, expires_at=utcnow() + SESSION_TTL))
        self.db.add(AnalyticsEvent(event_type=f"{agent}_open", user_id=self.principal.user_id))
        self.db.commit()
        return conv

    def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conv = self.db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != self.principal.user_id or conv.archived_at is not None:
            raise NotFoundError("Conversation was not found", code="CONVERSATION_NOT_FOUND")
        return conv

    def list_conversations(self, agent: str) -> list[tuple[Conversation, int]]:
        count = select(func.count(Message.id)).where(Message.conversation_id == Conversation.id).scalar_subquery()
        rows = self.db.execute(
            select(Conversation, count).where(Conversation.user_id == self.principal.user_id,
                                              Conversation.agent == AgentName(agent), Conversation.archived_at.is_(None))
            .order_by(Conversation.updated_at.desc()).limit(50)).all()
        return [(c, int(n)) for c, n in rows]

    def archive(self, conversation_id: uuid.UUID) -> None:
        conv = self.get_conversation(conversation_id)
        conv.archived_at = utcnow()
        self.db.commit()

    def messages(self, conversation_id: uuid.UUID) -> list[Message]:
        self.get_conversation(conversation_id)
        return list(self.db.scalars(select(Message).where(Message.conversation_id == conversation_id)
                                    .order_by(Message.created_at)))

    def session(self, conv: Conversation) -> AgentSession:
        s = self.db.scalar(select(AgentSession).where(AgentSession.conversation_id == conv.id))
        if s is None:
            s = AgentSession(conversation_id=conv.id, user_id=conv.user_id, agent=conv.agent, context={})
            self.db.add(s)
            self.db.flush()
        return s

    def memory(self, conversation_id: uuid.UUID) -> dict[str, Any]:
        conv = self.get_conversation(conversation_id)
        return SessionState.model_validate(self.session(conv).context or {}).public_view()

    # ------------------------------------------------------------ turns
    def _hints(self) -> dict[str, Any]:
        cats = self.db.execute(select(Category.slug, Category.name, Category.parent_id, Category.id)
                               .where(Category.deleted_at.is_(None), Category.is_active.is_(True))).all()
        by_id = {c.id: c.slug for c in cats}
        brands = [b for b in self.db.scalars(select(distinct(Product.brand)).where(
            Product.brand.is_not(None), Product.status == ProductStatus.ACTIVE, Product.deleted_at.is_(None))) if b]
        return {"categories": [{"slug": s, "name": n, "parent_slug": by_id.get(pid)} for s, n, pid, _ in cats],
                "brands": brands}

    def _history(self, conv: Conversation) -> list[dict[str, str]]:
        rows = list(self.db.scalars(select(Message).where(Message.conversation_id == conv.id)
                                    .order_by(Message.created_at.desc()).limit(self.settings.agent_max_history_messages)))
        return [{"role": m.role.value, "content": m.content[:1000]} for m in reversed(rows)
                if m.role in (MessageRole.USER, MessageRole.ASSISTANT)]

    def send(self, conversation_id: uuid.UUID, text: str, attachments: list[Attachment] | None = None,
             *, expected_action_id: str | None = None, status_cb: Callable[[str], None] | None = None
             ) -> dict[str, Any]:
        conv = self.get_conversation(conversation_id)
        agent = conv.agent.value
        self.authorize(agent)
        sess = self.session(conv)
        state = SessionState.model_validate(sess.context or {})
        if expected_action_id is not None:
            if state.pending_action is None or state.pending_action.id != expected_action_id:
                raise ConflictError("That action is no longer pending", code="ACTION_NOT_PENDING")

        history = self._history(conv)
        user_payload: dict[str, Any] = {}
        if attachments:
            user_payload["attachments"] = [{"name": a.name, "mime": a.mime, "size": len(a.data)} for a in attachments]
        if expected_action_id:
            user_payload["action"] = {"id": expected_action_id, "decision": "approve" if text == "yes" else "decline"}
        user_msg = Message(conversation_id=conv.id, role=MessageRole.USER, content=text or "(image)", payload=user_payload)
        self.db.add(user_msg)
        use_llm = bool(self._setting("agents.use_llm_when_available", True))
        engine = engine_for(agent, use_llm)
        wf = AgentWorkflow(session_id=sess.id, conversation_id=conv.id, user_id=self.principal.user_id,
                           agent=conv.agent, intent="pending", workflow_name="pending", status=WorkflowStatus.RUNNING)
        self.db.add(wf)
        self.db.flush()
        ctx = ToolContext(
            user_id=self.principal.user_id, roles=self.principal.roles, permissions=self.principal.permissions,
            agent=agent, seller_id=self.principal.seller_id, session_id=sess.id, workflow_id=wf.id,
            attachments={uuid.uuid4().hex[:12]: (a.data, a.mime) for a in attachments or []},
            services=AgentServices(self.db, self.principal),
        )
        executor = ToolExecutor(tool_registry(), DbToolRecorder(self.db),
                                max_calls=int(self._setting("agents.max_tool_calls_per_turn", 12)))
        outcome = engine.run_turn(text, state, ctx, executor, history=history, has_image=bool(attachments),
                                  hints=self._hints(), status_cb=status_cb)
        return self._persist(conv, sess, wf, outcome, user_msg)

    def _persist(self, conv: Conversation, sess: AgentSession, wf: AgentWorkflow, out: TurnOutcome,
                 user_msg: Message) -> dict[str, Any]:
        res = out.result
        wf.intent, wf.workflow_name = out.intent.intent, out.workflow
        wf.status = WorkflowStatus(res.status.value)
        wf.confidence, wf.nlu_mode = out.intent.confidence, out.intent.mode
        wf.model_name = out.intent.model
        wf.prompt_tokens, wf.completion_tokens = out.intent.prompt_tokens, out.intent.completion_tokens
        wf.steps, wf.safety_flags = out.steps, out.safety_flags
        wf.error_code, wf.latency_ms, wf.finished_at = res.error_code, out.latency_ms, utcnow()
        payload = {
            "blocks": [b.model_dump(mode="json") for b in res.blocks], "suggestions": res.suggestions,
            "steps": out.steps, "status": res.status.value, "intent": out.intent.intent, "workflow": out.workflow,
            "nlu_mode": out.intent.mode, "phrased_by": out.phrased_by, "safety_flags": out.safety_flags,
            "pending_action": out.state.pending_action.model_dump(mode="json") if out.state.pending_action else None,
        }
        msg = Message(conversation_id=conv.id, role=MessageRole.ASSISTANT, content=res.text, payload=payload,
                      workflow_id=wf.id)
        self.db.add(msg)
        sess.context = out.state.model_dump(mode="json")
        sess.pending_action = payload["pending_action"]
        sess.last_active_at, sess.expires_at = utcnow(), utcnow() + SESSION_TTL
        if not conv.title and user_msg.content and user_msg.content != "(image)":
            conv.title = user_msg.content[:80]
        conv.updated_at = utcnow()
        self.db.commit()
        log_event(logger, "agent_turn", agent=conv.agent.value, intent=wf.intent, workflow=wf.workflow_name,
                  status=wf.status.value, nlu_mode=wf.nlu_mode, latency_ms=wf.latency_ms,
                  tool_calls=len(wf.tool_calls), flags=out.safety_flags)
        return {"conversation_id": conv.id, "user_message": user_msg, "message": msg,
                "workflow": {"id": wf.id, "intent": wf.intent, "name": wf.workflow_name, "status": wf.status.value,
                             "confidence": wf.confidence, "nlu_mode": wf.nlu_mode, "steps": wf.steps,
                             "latency_ms": wf.latency_ms,
                             "tool_calls": [{"tool": c.tool_name, "status": c.status.value, "latency_ms": c.latency_ms}
                                            for c in wf.tool_calls]},
                "memory": out.state.public_view()}
