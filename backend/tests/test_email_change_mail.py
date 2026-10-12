import asyncio
import smtplib
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from uuid import uuid4

from auth_helpers import authenticated_id
from test_task_domain import authenticate
from test_user_cards import request_change, token_for

from app.core.config import get_settings
from app.models.email_change import EmailChangeRequest
from app.services.email_change_mail import EmailChangeMailService


async def test_real_local_smtp_delivery(client, db_session, monkeypatch, caplog):
    messages = []
    connections = set()

    async def sink(reader, writer):
        task = asyncio.current_task()
        connections.add(task)
        try:
            writer.write(b"220 localhost test sink\r\n")
            await writer.drain()
            while line := await reader.readline():
                command = line.upper()
                if command.startswith(b"EHLO"):
                    writer.write(b"250 localhost\r\n")
                elif command.startswith(b"DATA"):
                    writer.write(b"354 End with dot\r\n")
                    await writer.drain()
                    body = b""
                    while (part := await reader.readline()) not in (b".\r\n", b""):
                        body += part
                    messages.append(BytesParser(policy=policy.default).parsebytes(body))
                    writer.write(b"250 Accepted\r\n")
                elif command.startswith(b"QUIT"):
                    writer.write(b"221 Bye\r\n")
                    await writer.drain()
                    break
                else:
                    writer.write(b"250 OK\r\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            connections.discard(task)

    server = await asyncio.start_server(sink, "127.0.0.1", 0)
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", server.sockets[0].getsockname()[1])
    monkeypatch.setattr(settings, "smtp_security", "plain")
    monkeypatch.setattr(settings, "smtp_username", "")
    try:
        owner = await authenticate(client, uuid4())
        await request_change(client, owner)
        token = await token_for(db_session, owner)
        service = EmailChangeMailService(db_session)
        assert await service.process_one()
        assert not await service.process_one()
        assert len(messages) == 1
        assert messages[0]["To"] == "changed@example.com"
        assert "/#email-change=" + token in messages[0].get_content()
        assert token not in caplog.text and "changed@example.com" not in caplog.text
        row = await db_session.get(EmailChangeRequest, authenticated_id(owner))
        assert row.sent_at is not None and row.attempts == 1
    finally:
        server.close()
        await server.wait_closed()
        if connections:
            await asyncio.gather(*connections)


async def test_mail_retry_expiry_and_replacement(client, db_session, monkeypatch, caplog):
    owner = await authenticate(client, uuid4())
    await request_change(client, owner)
    token = await token_for(db_session, owner)

    def unavailable(_pending):
        raise smtplib.SMTPException("sensitive " + token)

    monkeypatch.setattr("app.services.email_change_mail.send_email_change", unavailable)
    service = EmailChangeMailService(db_session)
    assert await service.process_one()
    assert not await service.process_one()
    row = await db_session.get(EmailChangeRequest, authenticated_id(owner))
    assert row.attempts == 1 and row.sent_at is None
    assert token not in caplog.text
    await db_session.commit()
    await request_change(client, owner, "replacement@example.com")
    row = await db_session.get(EmailChangeRequest, authenticated_id(owner), populate_existing=True)
    assert row.attempts == 0 and row.sent_at is None
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert not await service.process_one()
    assert (
        await db_session.get(EmailChangeRequest, authenticated_id(owner), populate_existing=True)
        is None
    )
