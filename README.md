# element-bot

Element/Matrix ingestion service. It receives plaintext `m.room.message` text events
from rooms joined by the configured Matrix account and stores them in the shared
`messages` table with `platform = 'element'`. Matrix event IDs provide idempotency.

Configure the bot account in `orchestration/.env`:

```dotenv
ELEMENT_HOMESERVER=https://matrix.example.org
ELEMENT_USER_ID=@fingals:example.org
# Create a long-lived access token for the bot account in Element.
ELEMENT_ACCESS_TOKEN=...
```

The account must join any rooms to ingest. The service exposes its discovered rooms
and one-to-one room members to the Operations page, where Element group/room and
contact rules can be assigned to operations. Encrypted rooms require Matrix E2EE
configuration and are not ingested by this plaintext service.
