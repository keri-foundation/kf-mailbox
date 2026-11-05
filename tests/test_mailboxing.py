# -*- encoding: utf-8 -*-
"""Smoke the hosted mailbox deposit path used by Locksmith IPEX forwarding."""
import falcon
from falcon import testing
from keri.app import habbing
from keri.app.forwarding import StreamPoster
from keri.core.eventing import exchange, messagize
from keri.core.serdering import SerderKERI
from keri.kering import Kinds, Roles, Schemes, Vrsn_2_0

from kfmailbox.mailboxing import MailboxService


def test_two_controllers_exchange_through_registered_mailbox():
    service = MailboxService(temp=True, host="127.0.0.1", port=6732)
    try:
        with habbing.openHab(name="sender", temp=True, version=Vrsn_2_0) as (hby, sender), \
                habbing.openHab(name="receiver", temp=True, version=Vrsn_2_0) as (_, receiver), \
                habbing.openHab(name="outsider", temp=True, version=Vrsn_2_0) as (_, outsider):
            boot = testing.TestClient(service.bootApp)
            created = boot.simulate_post("/mailboxes", json={"aid": receiver.pre})
            assert created.status_code == 200
            body = created.json
            assert body["cid"] == receiver.pre
            assert body["eid"] == service.hab.pre
            assert body["oobis"] == [f"http://127.0.0.1:6732/oobi/{service.hab.pre}/controller"]

            again = boot.simulate_post("/mailboxes", json={"aid": receiver.pre})
            assert again.json["eid"] == service.hab.pre

            oobi = testing.TestClient(service.publicApp).simulate_get(f"/oobi/{service.hab.pre}/controller")
            assert oobi.status_code == 200
            assert oobi.headers["content-type"] == "application/cesr"
            assert service.hab.pre.encode() in oobi.content or len(oobi.content) > 0

            public = testing.TestClient(service.publicApp)
            path = f"/oobi/{receiver.pre}/mailbox/{service.hab.pre}"
            assert public.simulate_get(path).status_code == 404
            service.parser.parse(ims=bytearray(receiver.replay(gvrsn=Vrsn_2_0)), local=False)
            assert public.simulate_get(path).status_code == 404
            service.parser.parse(ims=receiver.makeEndRole(
                eid=service.hab.pre, role=Roles.mailbox, version=Vrsn_2_0), local=False)
            introduction = public.simulate_get(path)
            assert introduction.status_code == 200
            assert introduction.headers["content-type"] == "application/cesr"
            hby.psr.parse(ims=bytearray(introduction.content), local=False)
            assert sender.endsFor(receiver.pre)[Roles.mailbox][service.hab.pre][Schemes.http] == service.url
            service.hby.kevers.pop(receiver.pre)
            assert service.hby.db.states.get((receiver.pre,)) is not None
            assert public.simulate_get(path).status_code == 200

            exn = exchange(
                sender=sender.pre,
                receiver=receiver.pre,
                route="/echo",
                attributes={"note": "demo"},
                version=Vrsn_2_0,
                pvrsn=Vrsn_2_0,
                gvrsn=Vrsn_2_0,
                kind=Kinds.json,
            )
            poster = StreamPoster(hby=hby, hab=sender, recp=receiver.pre, topic="credential", version=Vrsn_2_0)
            framed = messagize(exn, sigers=sender.sign(ser=exn.raw), framed=True, gvrsn=Vrsn_2_0)
            poster.send(serder=exn, attachment=bytes(framed[exn.size:]))
            messengers = poster.deliver()
            request = list(messengers[0].client.requests)[0]
            assert request["method"] == "PUT"

            req = falcon.Request(testing.create_environ(
                method="PUT",
                body=bytes(request["body"]),
                headers={key: str(value) for key, value in request["headers"].items()},
            ))
            rep = falcon.Response()
            service.httpEnd.on_put(req, rep)
            assert rep.status == falcon.HTTP_204
            service.parser.parse(local=False)

            rows = list(service.mbx.cloneTopicIter(topic=f"{receiver.pre}/credential"))
            assert len(rows) == 1

            outsiderExn = exchange(
                sender=sender.pre,
                receiver=outsider.pre,
                route="/echo",
                attributes={"note": "no"},
                version=Vrsn_2_0,
                pvrsn=Vrsn_2_0,
                gvrsn=Vrsn_2_0,
                kind=Kinds.json,
            )
            hby.psr.parse(ims=bytearray(outsider.replay(gvrsn=Vrsn_2_0)), local=False)
            hby.psr.parse(ims=outsider.makeEndRole(
                eid=service.hab.pre, role=Roles.mailbox, version=Vrsn_2_0), local=False)
            poster = StreamPoster(hby=hby, hab=sender, recp=outsider.pre, topic="credential", version=Vrsn_2_0)
            outsiderFramed = messagize(
                outsiderExn,
                sigers=sender.sign(ser=outsiderExn.raw),
                framed=True,
                gvrsn=Vrsn_2_0,
            )
            poster.send(serder=outsiderExn, attachment=bytes(outsiderFramed[outsiderExn.size:]))
            request = list(poster.deliver()[0].client.requests)[0]
            req = falcon.Request(testing.create_environ(
                method="PUT",
                body=bytes(request["body"]),
                headers={key: str(value) for key, value in request["headers"].items()},
            ))
            service.httpEnd.on_put(req, falcon.Response())
            service.parser.parse(local=False)
            assert not list(service.mbx.cloneTopicIter(topic=f"{outsider.pre}/credential"))

            missing = boot.simulate_delete(f"/mailboxes/{outsider.pre}")
            assert missing.status_code == 404
            removed = boot.simulate_delete(f"/mailboxes/{receiver.pre}")
            assert removed.status_code == 204
            assert not service.registrar.allowed(receiver.pre)
            assert public.simulate_get(path).status_code == 404
    finally:
        service.close(clear=True)


def test_recipient_oobi_requires_registered_signed_mailbox_authorization():
    service = MailboxService(temp=True)
    try:
        with habbing.openHab(name="recipient", temp=True, version=Vrsn_2_0) as (_, recipient), \
                habbing.openHab(name="other", temp=True, version=Vrsn_2_0) as (_, other):
            public = testing.TestClient(service.publicApp)
            path = f"/oobi/{recipient.pre}/mailbox/{service.hab.pre}"
            service.parser.parse(ims=bytearray(recipient.replay(gvrsn=Vrsn_2_0)), local=False)
            authorization = recipient.makeEndRole(
                eid=service.hab.pre, role=Roles.mailbox, version=Vrsn_2_0)
            reply = SerderKERI(raw=authorization)
            forged = messagize(reply, sigers=other.sign(ser=reply.raw), gvrsn=Vrsn_2_0)
            service.registrar.allow(recipient.pre)
            service.parser.parse(ims=bytearray(forged), local=False)
            assert public.simulate_get(path).status_code == 404
            service.registrar.drop(recipient.pre)
            service.parser.parse(ims=bytearray(authorization), local=False)
            assert public.simulate_get(path).status_code == 404
            service.registrar.allow(recipient.pre)
            assert public.simulate_get(path).status_code == 200
            assert public.simulate_get(f"/oobi/{recipient.pre}").status_code == 200
            assert public.simulate_get(f"/oobi/{recipient.pre}/mailbox/{other.pre}").status_code == 404
            assert public.simulate_get(f"/oobi/{recipient.pre}/controller").status_code == 404
            service.parser.parse(ims=recipient.makeEndRole(
                eid=service.hab.pre, role=Roles.mailbox, allow=False, version=Vrsn_2_0), local=False)
            assert public.simulate_get(path).status_code == 404
    finally:
        service.close(clear=True)


def test_recipient_oobi_waits_for_witness_receipts():
    service = MailboxService(temp=True)
    try:
        with habbing.openHab(name="witness", temp=True, transferable=False,
                             version=Vrsn_2_0) as (hby, witness):
            recipient = hby.makeHab(name="witnessed-recipient", wits=[witness.pre],
                                    toad=1, version=Vrsn_2_0)
            service.registrar.allow(recipient.pre)
            service.parser.parse(ims=bytearray(recipient.replay(gvrsn=Vrsn_2_0)), local=False)
            authorization = recipient.makeEndRole(
                eid=service.hab.pre, role=Roles.mailbox, version=Vrsn_2_0)
            service.parser.parse(ims=bytearray(authorization), local=False)
            public = testing.TestClient(service.publicApp)
            path = f"/oobi/{recipient.pre}/mailbox/{service.hab.pre}"
            assert public.simulate_get(path).status_code == 404
            service.parser.parse(ims=witness.witness(recipient.kever.serder), local=False)
            service.kvy.processEscrows()
            service.parser.parse(ims=bytearray(authorization), local=False)
            assert public.simulate_get(path).status_code == 200
    finally:
        service.close(clear=True)


def test_boot_health_and_invalid_aid():
    service = MailboxService(temp=True)
    try:
        boot = testing.TestClient(service.bootApp)
        assert boot.simulate_get("/health").status_code == 204
        rejected = boot.simulate_post("/mailboxes", json={"aid": "not-an-aid"})
        assert rejected.status_code == 400
    finally:
        service.close(clear=True)
