"""Service for generating draft cost rules when gaps are detected."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from app.core.config import Settings
from app.schemas.rule_governance import MissingRuleCandidate, RuleGovernanceReport
from app.services.openai_client import OpenAIClient


PROMPT_TEMPLATE = """
You are a construction cost-estimating assistant. You are given information about a scope item that was
missing from the current cost rule catalog. Generate a YAML draft for a new cost rule that could cover this
scope. Follow these requirements:

- Provide realistic unit type, base unit cost, labor hours, labor rate, material cost per unit, equipment cost per unit.
- Include relevant multipliers (height, difficulty, material) if appropriate.
- Add a concise notes section explaining the assumptions.
- Keep YAML keys consistent with the existing catalog (name, keywords, unit_type, base_unit_cost, labor_hours_per_unit, labor_rate, material_cost_per_unit, equipment_cost_per_unit, waste_factor, multipliers, notes).
- Use snake_case for the rule name; base it on the item name when possible.
- When unsure about numeric values, choose conservative placeholders and mark them with TODO comments.

Return ONLY valid YAML for the rule. Do not wrap the YAML in triple backticks or any other formatting.

Missing rule context:
{context}
"""


class RuleAuthoringHelper:
    """Generates draft YAML rules for missing scope coverage."""

    def __init__(self, settings: Settings | None = None, *, openai_client: OpenAIClient | None = None) -> None:
        self.settings = settings or Settings()
        self.openai_client = openai_client or OpenAIClient(self.settings)

    def generate_drafts(
        self,
        governance_report: RuleGovernanceReport,
        project_output_dir: Path,
        *,
        force: bool = False,
    ) -> RuleGovernanceReport:
        """Generate YAML drafts for each missing rule in the report."""

        drafts_dir = project_output_dir / "rules_draft"
        drafts_dir.mkdir(parents=True, exist_ok=True)

        updated_candidates: list[MissingRuleCandidate] = []

        for candidate in governance_report.missing_rules:
            if candidate.draft_generated and not force:
                logger.debug(
                    "Skipping draft generation for %s (already generated)", candidate.item_name
                )
                updated_candidates.append(candidate)
                continue

            prompt_context = json.dumps(
                {
                    "item_name": candidate.item_name,
                    "description": candidate.description,
                    "detected_keywords": candidate.detected_keywords,
                    "probable_trade": candidate.probable_trade,
                    "evidence_snippet": candidate.evidence_snippet,
                    "metadata": candidate.metadata,
                },
                indent=2,
            )

            messages = [
                {
                    "role": "system",
                    "content": "You create cost rule YAML drafts for construction estimating.",
                },
                {
                    "role": "user",
                    "content": PROMPT_TEMPLATE.format(context=prompt_context),
                },
            ]

            logger.info("Generating rule draft for missing scope: %s", candidate.item_name)
            yaml_draft = self.openai_client.call_chat(
                messages,
                model=self.settings.openai_model,
                temperature=0.2,
                max_tokens=1200,
                stage_name="rule_authoring",
            )

            rule_filename = self._derive_rule_filename(candidate)
            output_path = drafts_dir / rule_filename
            output_path.write_text(yaml_draft.strip() + "\n", encoding="utf-8")
            logger.info("Draft rule saved to %s", output_path)

            candidate.draft_generated = True
            candidate.draft_filename = str(output_path.relative_to(project_output_dir))
            updated_candidates.append(candidate)

        governance_report.missing_rules = updated_candidates
        return governance_report

    def _derive_rule_filename(self, candidate: MissingRuleCandidate) -> str:
        slug = candidate.item_name.lower().replace(" ", "_")
        slug = "".join(ch for ch in slug if ch.isalnum() or ch == "_")
        if not slug:
            slug = "missing_rule"
        return f"{slug}.yml"
