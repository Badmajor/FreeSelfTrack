"""Privileged maintenance: python -m app.commands.attachments --help."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from app.core.object_storage import get_storage
from app.db.session import SessionFactory
from app.services.attachment_maintenance import AttachmentMaintenance
from app.services.errors import DomainError


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Attachment migration and quarantine administration")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="At revision 0015: verify and transfer legacy bytea files")
    commands.add_parser("cleanup", help="Remove unreferenced objects under the storage lock")
    pending = commands.add_parser("pending", help="List a bounded batch awaiting operator review")
    pending.add_argument("--limit", type=int, default=100, choices=range(1, 1001))
    export = commands.add_parser("export", help="Export privately for malware inspection")
    export.add_argument("id", type=UUID)
    export.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("review", help="Record an operator's malware review decision")
    review.add_argument("id", type=UUID)
    review.add_argument("--sha256", required=True)
    review.add_argument("--state", choices=("ready", "failed", "infected"), required=True)
    review.add_argument(
        "--reviewed-safe",
        action="store_true",
        help="Attest that these exact bytes were checked and found safe",
    )
    return root


async def run(args: argparse.Namespace) -> None:
    storage = get_storage()
    async with SessionFactory() as session:
        service = AttachmentMaintenance(session, storage)
        if args.command == "migrate":
            count = 0
            while await service.migrate_one():
                count += 1
            print(f"Verified and migrated {count} attachments")
        elif args.command == "cleanup":
            print(f"Removed {await service.cleanup()} orphan objects")
        elif args.command == "pending":
            rows = await service.repository.pending(args.limit)
            print(
                json.dumps(
                    [
                        {
                            "id": str(row.id),
                            "filename": row.filename,
                            "sha256": row.sha256,
                            "size": row.size,
                        }
                        for row in rows
                    ],
                    ensure_ascii=True,
                )
            )
        elif args.command == "review":
            if args.state == "ready" and not args.reviewed_safe:
                raise ValueError(
                    "Release requires --reviewed-safe after inspecting the exported checksum"
                )
            await service.review(args.id, args.sha256, args.state)
            print("Review recorded")
        elif args.command == "export":
            row = await service.repository.locked(args.id)
            if row is None or row.object_key is None:
                raise ValueError("Attachment not found or not migrated")
            # Exclusive creation and owner-only permissions; never overwrite operator files.
            import os

            with os.fdopen(
                os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
            ) as target:
                size, digest = await run_in_threadpool(storage.copy_to, row.object_key, target)
            if size != row.size or digest != row.sha256:
                args.output.unlink()
                raise ValueError("Object integrity verification failed")
            print(f"Exported quarantined bytes: sha256={digest}; do not open before scanning")


if __name__ == "__main__":
    try:
        asyncio.run(run(parser().parse_args()))
    except (DomainError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
