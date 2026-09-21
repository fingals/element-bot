# element-bot

Element/Matrix ingestion service. It receives plaintext `m.room.message` text events
from rooms joined by the configured Matrix account and stores them in the shared
`messages` table with `platform = 'element'`. Matrix event IDs provide idempotency.

Configure the bot account in `orchestration/.env`:

```dotenv
ELEMENT_HOMESERVER=https://matrix.example.org
ELEMENT_USER_ID=@fingals:example.org
ELEMENT_ACCESS_TOKEN=...
```

Use a dedicated Matrix account rather than copying an Element Desktop session
token. Element Desktop may rotate its access token. Open the web interface's
**Attach Phone** page and select **Create Element token** to create a separate
non-expiring bot session with password login. The password is sent only to the
selected homeserver, is not stored, and is cleared from the form after the
request. The homeserver can be changed in the form; the configured
`ELEMENT_HOMESERVER` is shown as its default placeholder. The flow refuses the
result if the homeserver still returns an expiring session.

Password login must be enabled for the account. SSO-only accounts need a
homeserver administrator to provision a dedicated bot token or account.

After updating `orchestration/.env`, recreate the service:

```text
docker compose --profile element --env-file .env -f docker-compose.yml up -d --force-recreate element-bot
```

The account must join any rooms to ingest. The service exposes its discovered rooms
and one-to-one room members to the Operations page, where Element group/room and
contact rules can be assigned to operations. Encrypted rooms require Matrix E2EE
configuration and are not ingested by this plaintext service.
