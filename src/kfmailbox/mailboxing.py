# -*- encoding: utf-8 -*-
"""
kfmailbox.mailboxing module

One operator mailbox with per-account registration.

kf-boot allocates an account onto this service. Deposit and poll stay here,
not on the witness and not inside kf-boot.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import falcon
from hio.base import doing
from hio.core import http
from hio.help import decking
from keri import help, kering
from keri.app import forwarding, habbing, storing
from keri.app.indirecting import HttpEnd, createHttpServer
from keri.core import coring, eventing, parsing
from keri.db import dbing, koming
from keri.end.ending import OOBIEnd
from keri.help import helping
from keri.peer import exchanging

logger = help.ogler.getLogger()


@dataclass
class AccountRegistration:
    aid: str = ""


class Registrar(dbing.LMDBer):
    """Accounts allowed to use this mailbox operator."""

    TailDirPath = ""
    AltTailDirPath = ".kf-mailbox"
    TempPrefix = "kf_mailbox_"

    def __init__(self, name="kf-mailbox", headDirPath=None, reopen=True, **kwa):
        self.accounts = None
        super().__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)

    def reopen(self, **kwa):
        super().reopen(**kwa)
        self.accounts = koming.Komer(
            db=self,
            subkey="acct.",
            klas=AccountRegistration,
        )

    def allow(self, aid: str) -> None:
        self.accounts.pin(keys=(aid,), val=AccountRegistration(aid=aid))

    def allowed(self, aid: str) -> bool:
        return self.accounts.get(keys=(aid,)) is not None

    def drop(self, aid: str) -> bool:
        if not self.allowed(aid):
            return False
        self.accounts.rem(keys=(aid,))
        return True


class RegisteredForwardHandler(forwarding.ForwardHandler):
    """Store /fwd bodies only for accounts kf-boot has registered."""

    def __init__(self, hby, mbx, registrar: Registrar):
        super().__init__(hby=hby, mbx=mbx)
        self.registrar = registrar

    def verify(self, serder, attachments=None, nests=None):
        if not super().verify(serder, attachments=attachments, nests=nests):
            return False
        modifiers = serder.ked.get("q") or {}
        receiver = modifiers.get("pre")
        return bool(receiver) and self.registrar.allowed(receiver)


class MailboxStart(doing.DoDoer):
    """Parse the public CESR intake and hand mailbox queries to the HTTP stream."""

    def __init__(self, hab, parser, kvy, exc, cues=None, queries=None, **opts):
        self.hab = hab
        self.parser = parser
        self.kvy = kvy
        self.exc = exc
        self.cues = cues if cues is not None else decking.Deck()
        self.queries = queries if queries is not None else decking.Deck()
        super().__init__(
            doers=[
                doing.doify(self.msgDo),
                doing.doify(self.escrowDo),
                doing.doify(self.cueDo),
            ],
            **opts,
        )

    def msgDo(self, tymth=None, tock=0.0, **kwa):
        self.wind(tymth)
        self.tock = tock
        yield self.tock
        done = yield from self.parser.parsator(local=False)
        return done

    def escrowDo(self, tymth=None, tock=0.0, **kwa):
        self.wind(tymth)
        self.tock = tock
        yield self.tock
        while True:
            self.kvy.processEscrows()
            self.exc.processEscrow()
            yield self.tock

    def cueDo(self, tymth=None, tock=0.0, **kwa):
        self.wind(tymth)
        self.tock = tock
        yield self.tock
        while True:
            while self.cues:
                cue = self.cues.popleft()
                if cue.get("kin") == "stream":
                    self.queries.append(cue)
                yield self.tock
            yield self.tock


class MailboxCollectionEnd:
    """``POST /mailboxes`` registers a controller AID on the shared operator."""

    def __init__(self, service: "MailboxService"):
        self.service = service

    def on_post(self, req, rep):
        body = req.get_media()
        aid = body.get("aid") if isinstance(body, dict) else None
        if not aid:
            raise falcon.HTTPBadRequest(description="missing AID for mailbox registration")
        try:
            prefixer = coring.Prefixer(qb64=aid)
        except Exception as ex:
            raise falcon.HTTPBadRequest(description=f"invalid AID for mailbox registration: {ex}") from ex

        self.service.registrar.allow(prefixer.qb64)
        rep.status = falcon.HTTP_200
        rep.content_type = "application/json"
        rep.data = json.dumps(self.service.allocation(prefixer.qb64)).encode("utf-8")


class MailboxResourceEnd:
    """``DELETE /mailboxes/{aid}`` drops one account registration.

    The path is the controller AID, not the operator AID. The operator stays up
    so other accounts on this mailbox keep working.
    """

    def __init__(self, service: "MailboxService"):
        self.service = service

    def on_delete(self, _req, rep, aid):
        try:
            prefixer = coring.Prefixer(qb64=aid)
        except Exception as ex:
            raise falcon.HTTPBadRequest(description=f"invalid AID for mailbox registration: {ex}") from ex
        if not self.service.registrar.drop(prefixer.qb64):
            raise falcon.HTTPNotFound(description=f"mailbox registration for {prefixer.qb64} was not found")
        rep.status = falcon.HTTP_204


class HealthEnd:
    @staticmethod
    def on_get(_req, rep):
        rep.status = falcon.HTTP_NO_CONTENT


def publicUrl(scheme: str, host: str, port: int) -> str:
    if (scheme == kering.Schemes.http and port == 80) or (scheme == kering.Schemes.https and port == 443):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


class MailboxService(doing.DoDoer):
    """Shared mailbox operator plus the account registry kf-boot drives."""

    def __init__(
        self,
        *,
        base="",
        temp=False,
        headDirPath=None,
        scheme=kering.Schemes.http,
        host="127.0.0.1",
        port=6732,
        publicHost=None,
        publicPort=None,
    ):
        self.scheme = scheme
        self.host = host
        self.port = port
        self.publicHost = publicHost or host
        self.publicPort = port if publicPort is None else publicPort
        self.url = publicUrl(scheme, self.publicHost, self.publicPort)

        self.registrar = Registrar(name="kf-mailbox", headDirPath=headDirPath, temp=temp, base=base)
        self.hby = habbing.Habery(
            name="kf-mailbox",
            base=base,
            temp=temp,
            headDirPath=headDirPath,
            version=kering.Vrsn_2_0,
        )
        self.hab = self.hby.habByName("operator")
        if self.hab is None:
            self.hab = self.hby.makeHab(
                name="operator",
                transferable=False,
                version=kering.Vrsn_2_0,
            )

        self.mbx = storing.Mailboxer(name=self.hab.name, temp=temp, base=base)
        self.qrycues = decking.Deck()
        cues = decking.Deck()
        forwarder = RegisteredForwardHandler(hby=self.hby, mbx=self.mbx, registrar=self.registrar)
        self.exc = exchanging.Exchanger(hby=self.hby, handlers=[forwarder])
        self.kvy = eventing.Kevery(db=self.hby.db, lax=True, local=False, rvy=self.hby.rvy, cues=cues)
        self.kvy.registerReplyRoutes(router=self.hby.rtr)
        self.parser = parsing.Parser(
            framed=True,
            kvy=self.kvy,
            exc=self.exc,
            rvy=self.hby.rvy,
            version=kering.Vrsn_2_0,
        )
        self.hab.kvy = self.kvy
        self.hab.psr = self.parser
        self._publishLocation()

        self.httpEnd = HttpEnd(rxbs=self.parser.ims, mbx=self.mbx, qrycues=self.qrycues)
        self.bootApp = falcon.App()
        self.bootApp.add_route("/mailboxes", MailboxCollectionEnd(self))
        self.bootApp.add_route("/mailboxes/{aid}", MailboxResourceEnd(self))
        self.bootApp.add_route("/health", HealthEnd())

        self.publicApp = falcon.App()
        self.publicApp.add_route("/", self.httpEnd)
        oobi = OOBIEnd(hby=self.hby, default=self.hab.pre)
        self.publicApp.add_route("/oobi", oobi)
        self.publicApp.add_route("/oobi/{aid}", oobi)
        self.publicApp.add_route("/oobi/{aid}/{role}", oobi)
        self.publicApp.add_route("/oobi/{aid}/{role}/{eid}", oobi)

        starter = MailboxStart(
            hab=self.hab,
            parser=self.parser,
            kvy=self.kvy,
            exc=self.exc,
            cues=cues,
            queries=self.qrycues,
        )
        super().__init__(doers=[starter])

    def _publishLocation(self) -> None:
        stamp = helping.nowIso8601()
        msgs = bytearray()
        msgs.extend(
            self.hab.makeEndRole(
                eid=self.hab.pre,
                role=kering.Roles.controller,
                stamp=stamp,
            )
        )
        msgs.extend(
            self.hab.makeLocScheme(
                url=self.url,
                scheme=self.scheme,
                stamp=stamp,
            )
        )
        self.hab.psr.parse(ims=msgs)

    def allocation(self, aid: str) -> dict:
        return {
            "cid": aid,
            "eid": self.hab.pre,
            "name": "kf-mailbox",
            "oobis": [f"{self.url}/oobi/{self.hab.pre}/controller"],
            "status": "allocated",
            "url": self.url,
        }

    def close(self, clear=False) -> None:
        self.mbx.close()
        self.hby.close(clear=clear)
        self.registrar.close(clear=clear)


def setup(
    bootHost="127.0.0.1",
    bootPort=6731,
    base="",
    temp=False,
    headDirPath=None,
    host="127.0.0.1",
    port=6732,
    scheme=None,
    publicUrlValue=None,
    keypath=None,
    certpath=None,
    cafilepath=None,
):
    """Build boot and public HTTP servers around one mailbox operator.

    Parameters:
        bootHost (str): management API bind host.
        bootPort (int): management API bind port.
        publicUrlValue (str | None): URL wallets should use. When omitted,
            the public bind host and port are advertised.
    """
    publicHost = host
    publicPort = port
    publicScheme = scheme or kering.Schemes.http
    if publicUrlValue:
        parts = urlsplit(publicUrlValue)
        publicScheme = parts.scheme or publicScheme
        publicHost = parts.hostname or publicHost
        publicPort = parts.port or (443 if publicScheme == kering.Schemes.https else 80)

    service = MailboxService(
        base=base,
        temp=temp,
        headDirPath=headDirPath,
        scheme=publicScheme,
        host=host,
        port=port,
        publicHost=publicHost,
        publicPort=publicPort,
    )
    bootServer = createHttpServer(host=bootHost, port=bootPort, app=service.bootApp, keypath=keypath, certpath=certpath, cafilepath=cafilepath)
    publicServer = createHttpServer(host=host, port=port, app=service.publicApp, keypath=keypath, certpath=certpath, cafilepath=cafilepath)
    doers = [
        service,
        http.ServerDoer(server=bootServer),
        http.ServerDoer(server=publicServer),
    ]
    return doers
