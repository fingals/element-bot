import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import asyncpg
from fastapi import FastAPI
from nio import AsyncClient, RoomMessageText, SyncError
from uvicorn import Config, Server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class ElementIngestor:
    def __init__(self, pool: asyncpg.Pool, client: AsyncClient):
        self.pool = pool
        self.client = client

    async def on_room_message(self, room, event: RoomMessageText) -> None:
        if not event.body or not event.event_id:
            return

        timestamp = event.server_timestamp or int(datetime.now(timezone.utc).timestamp() * 1000)
        room_name = getattr(room, "display_name", None) or room.room_id
        sender = event.sender

        async with self.pool.acquire() as conn:
            inserted = await conn.fetchrow(
                """
                INSERT INTO messages (
                    platform, external_id, source, source_uuid, source_name,
                    "timestamp", type, text, group_id, group_name, raw_message,
                    processed, created_at, classification_status
                )
                VALUES (
                    'element', $1, $2, $2, $3, $4, 'ELEMENT_MESSAGE', $5, $6, $7,
                    $8::jsonb, FALSE, NOW(), 'pending'
                )
                ON CONFLICT (platform, external_id) WHERE external_id IS NOT NULL DO NOTHING
                RETURNING id
                """,
                event.event_id,
                sender,
                self._member_name(room, sender),
                timestamp,
                event.body,
                room.room_id,
                room_name,
                json.dumps(getattr(event, "source", {})),
            )

        if inserted:
            logger.info("Ingested Element event %s from %s in %s", event.event_id, sender, room_name)

    @staticmethod
    def _member_name(room, user_id: str) -> str:
        member = getattr(room, "users", {}).get(user_id)
        return getattr(member, "display_name", None) or user_id

    def sources(self) -> dict[str, list[dict[str, str]]]:
        groups = []
        contacts: dict[str, str] = {}

        for room in self.client.rooms.values():
            room_id = room.room_id
            room_name = getattr(room, "display_name", None) or room_id
            groups.append({"id": room_id, "name": room_name})

            members = [
                (user_id, self._member_name(room, user_id))
                for user_id in getattr(room, "users", {})
                if user_id != self.client.user_id
            ]
            if len(members) == 1:
                contacts[members[0][0]] = members[0][1]

        return {
            "groups": sorted(groups, key=lambda group: group["name"].lower()),
            "contacts": [
                {"id": user_id, "name": name}
                for user_id, name in sorted(contacts.items(), key=lambda item: item[1].lower())
            ],
        }


ingestor: ElementIngestor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Element Bot API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sources")
async def sources() -> dict[str, list[dict[str, str]]]:
    return ingestor.sources() if ingestor else {"groups": [], "contacts": []}


async def create_pool(db_url: str) -> asyncpg.Pool:
    url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    for attempt in range(10):
        try:
            return await asyncpg.create_pool(url, min_size=1, max_size=5)
        except (asyncpg.PostgresError, OSError) as exc:
            logger.warning("Database connection attempt %s failed: %s", attempt + 1, exc)
            await asyncio.sleep(3)
    raise RuntimeError("Could not connect to the database")


async def login_client() -> AsyncClient:
    homeserver = os.environ["ELEMENT_HOMESERVER"].rstrip("/")
    user_id = os.environ["ELEMENT_USER_ID"]
    access_token = os.getenv("ELEMENT_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise RuntimeError("ELEMENT_ACCESS_TOKEN must be configured for Element ingestion")

    client = AsyncClient(homeserver, user_id)
    client.access_token = access_token
    return client


async def main() -> None:
    global ingestor

    for name in ("ELEMENT_HOMESERVER", "ELEMENT_USER_ID"):
        if not os.getenv(name, "").strip():
            raise RuntimeError(f"{name} must be configured for Element ingestion")

    pool = await create_pool(os.environ["DATABASE_URL"])
    client = await login_client()
    ingestor = ElementIngestor(pool, client)
    client.add_event_callback(ingestor.on_room_message, RoomMessageText)

    server = Server(Config(app, host="0.0.0.0", port=8091, log_level="warning"))
    server_task = asyncio.create_task(server.serve())
    logger.info("Starting Element/Matrix ingestion from %s", client.homeserver)

    try:
        since = None
        while True:
            response = await client.sync(timeout=30_000, since=since, full_state=since is None)
            if isinstance(response, SyncError):
                logger.warning("Element sync failed: %s", response)
                await asyncio.sleep(5)
                continue
            since = response.next_batch
    finally:
        server.should_exit = True
        await server_task
        await client.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
