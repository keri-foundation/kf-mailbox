# -*- encoding: utf-8 -*-
"""Smoke the hosted mailbox deposit path used by Locksmith IPEX forwarding."""
import falcon
from falcon import testing
from keri.app import habbing
from keri.app.forwarding import StreamPoster
from keri.core.eventing import exchange, messagize
from keri.kering import Kinds, Roles, Schemes, Vrsn_2_0

from kfmailbox.mailboxing import MailboxService


def test_two_controllers_exchange_through_registered_mailbox(monkeypatch):
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
            monkeypatch.setattr(sender, "endsFor", lambda pre: {
                Roles.mailbox: {service.hab.pre: {Schemes.http: "http://127.0.0.1:6732"}},
            })
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
