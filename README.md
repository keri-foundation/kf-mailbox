# kf-mailbox

KERI Foundation mailbox for staging and demos.

This service is the store-and-forward data plane. `kf-boot` allocates it and binds each onboarded account to it. It does not receipt KELs and it does not run inside the witness.

One non-transferable operator AID serves every account on this process. `POST /mailboxes` registers a controller AID. Messages are stored only for registered controllers, keyed by `{recipient AID}/{topic}`. Deleting a registration does not stop the operator.

## Run

```bash
uv sync
uv run kf-mailbox serve
```

`uv sync` installs the project and the `dev` group (pytest, ruff) into `.venv`. Python 3.14 is pinned in `.python-version`. `uv sync --no-dev` installs the service without the dev tools.

Defaults:

| Surface | Bind | Role |
| --- | --- | --- |
| Boot | `127.0.0.1:6731` | `POST /mailboxes`, `DELETE /mailboxes/{aid}`, `GET /health` |
| Public | `127.0.0.1:6732` | CESR `PUT /` deposit, `POST /` `qry`/`mbx` poll, `GET /oobi/...` |

`KF_MAILBOX_PUBLIC_URL` is the URL wallets should use when it differs from the bind address (for example `http://192.0.2.10:6732`).

Point kf-boot at the boot API and advertise the public URL:

```bash
export KF_BOOT_MBX_BOOT_URL=http://127.0.0.1:6731
export KF_BOOT_MBX_PUBLIC_URL=http://127.0.0.1:6732
```

## Boot API

`POST /mailboxes` with `{"aid": "<controller AID>"}` returns:

```json
{"cid": "<controller>", "eid": "<operator>", "name": "kf-mailbox", "oobis": [".../oobi/<operator>/controller"], "status": "allocated", "url": "http://127.0.0.1:6732"}
```

The call is idempotent for the same controller. `DELETE /mailboxes/{aid}` removes that controller. `{aid}` is the account AID, not the operator AID.

## Wallet path

After kf-boot onboarding, the session reply includes `mailbox.eid` and `mailbox.oobi`. Locksmith resolves the OOBI, anchors `Roles.mailbox` on the account AID, and polls that operator with `MailboxDirector`.
