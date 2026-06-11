from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import structlog

from startup_ops_agent.models import (
    Account,
    AccountBrief,
    ActionType,
    RecommendedAction,
    RiskLevel,
    RiskSignal,
    Task,
)
from startup_ops_agent.policy import Actor, ensure_action_allowed, requires_approval
from startup_ops_agent.repository import JsonRepository

logger = structlog.get_logger(__name__)


class NotFoundError(RuntimeError):
    pass


class SafetyInvariantError(RuntimeError):
    """Raised when a plan would violate a hard safety invariant (fail-closed)."""


def _days_until(value: date, today: date) -> int:
    return (value - today).days


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return digest


class StartupOpsService:
    def __init__(self, repository: JsonRepository) -> None:
        self.repository = repository

    def build_account_brief(
        self,
        *,
        account_id: str,
        actor: Actor,
        today: date | None = None,
    ) -> AccountBrief:
        today = today or date.today()
        account = self._get_account(account_id)
        opportunities = [
            opportunity
            for opportunity in self.repository.opportunities()
            if opportunity.account_id == account.account_id
        ]
        interactions = [
            interaction
            for interaction in self.repository.interactions()
            if interaction.account_id == account.account_id
        ]
        support_tickets = [
            ticket
            for ticket in self.repository.support_tickets()
            if ticket.account_id == account.account_id
        ]
        open_tasks = [
            task
            for task in self.repository.tasks()
            if task.account_id == account.account_id and task.status in {"draft", "approved"}
        ]

        risk_signals = self._score_risks(
            account=account,
            opportunities=opportunities,
            interactions=interactions,
            support_tickets=support_tickets,
            today=today,
        )
        recommended_actions = self._recommend_actions(risk_signals)

        logger.info(
            "account_brief_built",
            actor_id=actor.actor_id,
            actor_role=actor.role.value,
            account_id=account.account_id,
            risk_count=len(risk_signals),
            recommended_action_count=len(recommended_actions),
        )
        self.repository.append_audit_event(
            {
                "event": "account_brief_built",
                "actor_id": actor.actor_id,
                "actor_role": actor.role.value,
                "account_id": account.account_id,
                "source_ids": self._source_ids(risk_signals),
            }
        )
        return AccountBrief(
            account=account,
            opportunities=opportunities,
            interactions=interactions,
            support_tickets=support_tickets,
            open_tasks=open_tasks,
            risk_signals=risk_signals,
            recommended_actions=recommended_actions,
        )

    def create_task_draft(
        self,
        *,
        account_id: str,
        actor: Actor,
        title: str,
        action_type: ActionType,
        source_ids: list[str],
    ) -> Task:
        ensure_action_allowed(actor, action_type)
        account = self._get_account(account_id)
        idempotency_key = _stable_id(
            account.account_id,
            action_type.value,
            title,
            *sorted(source_ids),
        )
        tasks = self.repository.tasks()
        for task in tasks:
            if task.idempotency_key == idempotency_key:
                logger.info(
                    "task_draft_reused",
                    actor_id=actor.actor_id,
                    account_id=account.account_id,
                    task_id=task.task_id,
                    action_type=action_type.value,
                )
                return task

        task = Task(
            task_id=f"task-{idempotency_key}",
            account_id=account.account_id,
            action_type=action_type,
            title=title,
            owner_id=actor.actor_id,
            created_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
            source_ids=source_ids,
        )
        tasks.append(task)
        self.repository.save_tasks(tasks)
        self.repository.append_audit_event(
            {
                "event": "task_draft_created",
                "actor_id": actor.actor_id,
                "actor_role": actor.role.value,
                "account_id": account.account_id,
                "task_id": task.task_id,
                "action_type": action_type.value,
                "requires_approval": requires_approval(action_type),
                "source_ids": source_ids,
            }
        )
        logger.info(
            "task_draft_created",
            actor_id=actor.actor_id,
            account_id=account.account_id,
            task_id=task.task_id,
            action_type=action_type.value,
            requires_approval=requires_approval(action_type),
        )
        return task

    def _get_account(self, account_id: str) -> Account:
        for account in self.repository.accounts():
            if account.account_id == account_id:
                return account
        raise NotFoundError(f"Account not found: {account_id}")

    def _score_risks(
        self,
        *,
        account: Account,
        opportunities: list,
        interactions: list,
        support_tickets: list,
        today: date,
    ) -> list[RiskSignal]:
        risks: list[RiskSignal] = []
        days_to_renewal = _days_until(account.renewal_date, today)
        if account.health_score < 65 and days_to_renewal <= 90:
            risks.append(
                RiskSignal(
                    risk_id=_stable_id(account.account_id, "renewal", str(account.health_score)),
                    level=RiskLevel.high,
                    category="renewal",
                    summary=(
                        f"Health score is {account.health_score} with renewal in "
                        f"{days_to_renewal} days."
                    ),
                    source_ids=[account.account_id],
                )
            )

        open_critical = [
            ticket
            for ticket in support_tickets
            if ticket.status != "resolved" and ticket.severity in {"high", "critical"}
        ]
        if open_critical:
            risks.append(
                RiskSignal(
                    risk_id=_stable_id(
                        account.account_id,
                        "support",
                        *[t.ticket_id for t in open_critical],
                    ),
                    level=RiskLevel.high,
                    category="support",
                    summary=f"{len(open_critical)} high-severity support issue(s) remain open.",
                    source_ids=[ticket.ticket_id for ticket in open_critical],
                )
            )

        stale_opportunities = [
            opportunity
            for opportunity in opportunities
            if (today - opportunity.last_activity_date).days >= 14
        ]
        if stale_opportunities:
            risks.append(
                RiskSignal(
                    risk_id=_stable_id(
                        account.account_id,
                        "stale-opportunity",
                        *[opportunity.opportunity_id for opportunity in stale_opportunities],
                    ),
                    level=RiskLevel.medium,
                    category="pipeline",
                    summary=(
                        f"{len(stale_opportunities)} open opportunity(s) "
                        "have no activity in 14+ days."
                    ),
                    source_ids=[opportunity.opportunity_id for opportunity in stale_opportunities],
                )
            )

        recent_negative = [
            interaction
            for interaction in interactions
            if (
                interaction.sentiment == "negative"
                and (today - interaction.occurred_at.date()).days <= 30
            )
        ]
        if recent_negative:
            risks.append(
                RiskSignal(
                    risk_id=_stable_id(
                        account.account_id,
                        "sentiment",
                        *[interaction.interaction_id for interaction in recent_negative],
                    ),
                    level=RiskLevel.medium,
                    category="relationship",
                    summary=(
                        f"{len(recent_negative)} negative customer interaction(s) "
                        "in the last 30 days."
                    ),
                    source_ids=[interaction.interaction_id for interaction in recent_negative],
                )
            )

        return sorted(risks, key=lambda risk: (risk.level != RiskLevel.high, risk.category))

    def _recommend_actions(self, risks: list[RiskSignal]) -> list[RecommendedAction]:
        recommendations: list[RecommendedAction] = []
        for risk in risks:
            if risk.category == "support":
                action_type = ActionType.create_task
                title = "Escalate unresolved customer support risk"
            elif risk.category == "renewal":
                action_type = ActionType.draft_email
                title = "Draft executive renewal recovery email"
            elif risk.category == "pipeline":
                action_type = ActionType.create_task
                title = "Schedule next pipeline activity"
            else:
                action_type = ActionType.create_task
                title = "Prepare customer sentiment recovery follow-up"

            recommendations.append(
                RecommendedAction(
                    action_type=action_type,
                    title=title,
                    reason=risk.summary,
                    requires_approval=requires_approval(action_type),
                    source_ids=risk.source_ids,
                )
            )
        return recommendations

    def _source_ids(self, risks: list[RiskSignal]) -> list[str]:
        source_ids: list[str] = []
        for risk in risks:
            source_ids.extend(risk.source_ids)
        return sorted(set(source_ids))
