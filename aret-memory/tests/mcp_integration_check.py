"""Vérification de protocole MCP stdio pour ARET-MMU."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    memory_dir = root / ".aret-memory-integration"
    env = {**os.environ, "ARET_MEMORY_DIR": str(memory_dir), "ARET_WRITE_ENABLED": "false"}
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(root / "aret_mmu_server.py")],
        env=env,
        cwd=str(root),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            required = {
                "aret_boot", "aret_restore", "aret_get_front", "aret_get_resume_brief", "aret_get_resume_protocol", "aret_acknowledge_resume", "aret_find", "aret_read", "aret_read_batch",
                "aret_get_forensics", "aret_get_proofs", "aret_get_related", "aret_get_roadmap", "aret_read_artifact",
                "aret_append_knowledge", "aret_update_front", "aret_replace_front", "aret_prepare_handoff", "aret_rebuild_front",
                "aret_record_proof", "aret_attach_proof", "aret_invalidate_proof", "aret_add_relation",
                "aret_supersede_relation", "aret_register_component", "aret_register_function", "aret_register_brick", "aret_update_brick",
                "aret_rebuild_index", "aret_export", "aret_export_bundle", "aret_import_bundle", "aret_export_roadmap",
                "aret_run_oracle", "aret_get_pipeline_catalog", "aret_get_toolchain_status", "aret_run_pipeline",
                "aret_get_pipeline_runs", "aret_read_pipeline_artifact", "aret_get_assets", "aret_register_asset",
                "aret_sync_memory", "aret_export_reference_91",
            }
            missing = required - names
            unexpected = names - required
            if missing or unexpected:
                raise AssertionError(f"Inventaire MCP incohérent ; manquants={sorted(missing)}, inattendus={sorted(unexpected)}")
            handoff_tool = next(tool for tool in tools.tools if tool.name == "aret_prepare_handoff")
            handoff_properties = handoff_tool.input_schema.get("properties", {})
            required_handoff_fields = {
                "technical_checkpoint_state", "technical_target", "technical_change",
                "execution_state", "last_validation", "immediate_actions",
            }
            if required_handoff_fields - set(handoff_properties):
                raise AssertionError("Contrat MCP handoff V1.2 incomplet")
            if "technical_checkpoint_state" not in set(handoff_tool.input_schema.get("required", [])):
                raise AssertionError("technical_checkpoint_state doit être obligatoire")
            response = await session.call_tool("aret_boot", {})
            if not response.structured_content or response.structured_content.get("ok") is not True:
                raise AssertionError(f"Réponse aret_boot inattendue : {response}")
            result = response.structured_content["result"]
            if result["server"] != "ARET-MMU" or result["write_enabled"] is not False:
                raise AssertionError(f"Bootstrap incohérent : {result}")

            # V1.4 : une capacité ARET cataloguée est sélectionnée via MCP avant toute
            # commande locale équivalente. Les trois plans restent en dry_run, donc sans mutation.
            catalog_response = await session.call_tool("aret_get_pipeline_catalog", {})
            catalog_payload = catalog_response.structured_content
            if not catalog_payload or catalog_payload.get("ok") is not True:
                raise AssertionError(f"Catalogue MCP inattendu : {catalog_response}")
            catalog = catalog_payload["result"]
            catalog_names = {
                item["name"]
                for entries in catalog.get("policies", {}).values()
                for item in entries
                if isinstance(item, dict) and "name" in item
            }
            required_governance_pipelines = {"run_relay_diff", "run_magicdiv_check", "run_regression_gate"}
            if required_governance_pipelines - catalog_names:
                raise AssertionError("Catalogue V1.4 incomplet pour les capacités ARET réutilisables")
            toolchain_response = await session.call_tool("aret_get_toolchain_status", {})
            toolchain_payload = toolchain_response.structured_content
            if not toolchain_payload or toolchain_payload.get("ok") is not True:
                raise AssertionError(f"Toolchain MCP inattendue : {toolchain_response}")
            for pipeline in sorted(required_governance_pipelines):
                plan_response = await session.call_tool("aret_run_pipeline", {
                    "pipeline": pipeline, "parameters": {}, "dry_run": True,
                    "confirm_apply": False, "confirm_network": False, "confirm_sensitive": False,
                })
                plan_payload = plan_response.structured_content
                if not plan_payload or plan_payload.get("ok") is not True:
                    raise AssertionError(f"Plan MCP V1.4 inattendu pour {pipeline} : {plan_response}")
                plan = plan_payload["result"]
                if plan.get("pipeline") != pipeline or plan.get("dry_run") is not True:
                    raise AssertionError(f"Plan V1.4 invalide pour {pipeline} : {plan}")
            acknowledgement = await session.call_tool("aret_acknowledge_resume", {
                "working_rules": "Les règles imposent FIND puis READ, des verdicts honnêtes et une preuve PASS admissible pour PROVEN.",
                "current_state": "Le Front et la roadmap déterminent l’état actif, les bloqueurs et l’objectif opérationnel à poursuivre.",
                "capabilities": "Les outils MCP, oracles, assets et pipelines fermés sont disponibles ; dry run précède les actions à risque.",
                "git_state": "La branche, les derniers commits et l’état de l’arbre Git ont été examinés dans le contexte de reprise injecté.",
                "risks_and_limits": "Aucun SQL, shell ou push Git arbitraire ; auto_push reste faux et le document 91 demeure non applicable.",
                "next_action": "Je vais confirmer le point de départ avec le Front avant une action ciblée, mesurée et conforme aux garde-fous.",
                "resume_contract_hash": "a" * 64,
            })
            if not acknowledgement.structured_content or acknowledgement.structured_content.get("ok") is not True:
                raise AssertionError(f"Confirmation de reprise inattendue : {acknowledgement}")
    print(f"MCP stdio validé : {len(names)} outils déclarés, aret_boot opérationnel.")


if __name__ == "__main__":
    asyncio.run(main())
