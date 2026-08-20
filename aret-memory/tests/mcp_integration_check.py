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
                "aret_append_knowledge", "aret_update_front", "aret_replace_front", "aret_rebuild_front",
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
            response = await session.call_tool("aret_boot", {})
            if not response.structured_content or response.structured_content.get("ok") is not True:
                raise AssertionError(f"Réponse aret_boot inattendue : {response}")
            result = response.structured_content["result"]
            if result["server"] != "ARET-MMU" or result["write_enabled"] is not False:
                raise AssertionError(f"Bootstrap incohérent : {result}")
            acknowledgement = await session.call_tool("aret_acknowledge_resume", {
                "working_rules": "Les règles imposent FIND puis READ, des verdicts honnêtes et une preuve PASS admissible pour PROVEN.",
                "current_state": "Le Front et la roadmap déterminent l’état actif, les bloqueurs et l’objectif opérationnel à poursuivre.",
                "capabilities": "Les outils MCP, oracles, assets et pipelines fermés sont disponibles ; dry run précède les actions à risque.",
                "git_state": "La branche, les derniers commits et l’état de l’arbre Git ont été examinés dans le contexte de reprise injecté.",
                "risks_and_limits": "Aucun SQL, shell ou push Git arbitraire ; auto_push reste faux et le document 91 demeure non applicable.",
                "next_action": "Je vais confirmer le point de départ avec le Front avant une action ciblée, mesurée et conforme aux garde-fous.",
            })
            if not acknowledgement.structured_content or acknowledgement.structured_content.get("ok") is not True:
                raise AssertionError(f"Confirmation de reprise inattendue : {acknowledgement}")
    print(f"MCP stdio validé : {len(names)} outils déclarés, aret_boot opérationnel.")


if __name__ == "__main__":
    asyncio.run(main())
