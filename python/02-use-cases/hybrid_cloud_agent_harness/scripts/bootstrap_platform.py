"""Create/attach AgentKit resources without writing credentials to the repo."""

from __future__ import annotations

import argparse
import subprocess
import sys


def run(*args: str) -> str:
    command = ["agentkit", *args]
    print("+", " ".join(command))
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--region", default="cn-sh")
    parser.add_argument("--memory-name", default="hybrid_customer_service_memory")
    parser.add_argument("--memory-id", help="Existing/console-created AgentKit MemoryId")
    parser.add_argument(
        "--knowledge-id",
        help="Existing published AgentKit KnowledgeId backed by hybrid-cloud Cloud Search",
    )
    args = parser.parse_args()

    memory_id = args.memory_id
    if not memory_id:
        existing_memory = run(
            "memory", "list", "--name", args.memory_name, "--region", args.region, "--quiet"
        )
        if existing_memory:
            memory_id = existing_memory.splitlines()[-1].strip()
        else:
            try:
                run(
                    "memory",
                    "create",
                    "--name",
                    args.memory_name,
                    "--description",
                    "Hybrid customer-service preferences and summaries",
                    "--provider-type",
                    "MEM0",
                    "--strategy",
                    "Summary:conversation_summary",
                    "--strategy",
                    "Semantic:customer_facts",
                    "--strategy",
                    "UserPreference:customer_preferences",
                    "--region",
                    args.region,
                )
            except subprocess.CalledProcessError as exc:
                print(exc.stderr or exc.stdout, file=sys.stderr)
                raise SystemExit(
                    "Memory creation failed. Create a managed MEM0 memory in the console, "
                    "select its embedding/LLM models, then rerun with --memory-id <id>."
                ) from exc
            memory_id = (
                run(
                    "memory",
                    "list",
                    "--name",
                    args.memory_name,
                    "--region",
                    args.region,
                    "--quiet",
                )
                .splitlines()[-1]
                .strip()
            )

    knowledge_id = args.knowledge_id

    update = [
        "runtime",
        "update",
        "--runtime-id",
        args.runtime_id,
        "--memory-id",
        memory_id,
        "--region",
        args.region,
    ]
    if knowledge_id:
        update.extend(["--knowledge-id", knowledge_id])
    run(*update)
    print(f"Memory attached: {memory_id}")
    print(f"Knowledge attached: {knowledge_id or 'not configured'}")


if __name__ == "__main__":
    main()
