from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Callable, Deque, Dict, Iterable, List, Tuple

from .link_quality import LinkQualitySimulator
from .models import LinkMetric, QualitySnapshot
from .toxiproxy_control import (
    ALL_LINKS,
    NODE_IDS,
    ProxyEndpoint,
    ToxiproxyHttpClient,
    ToxiproxyServerProcess,
    build_proxy_endpoints,
)


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class ProbeOutcome:
    elapsed_s: float
    link_key: str
    seq: int
    ok: bool
    rtt_ms: float
    configured_delay_ms: float
    configured_loss_rate: float
    error: str = ""


class VppNodeServer:
    """One virtual power-plant node exposed as a real TCP socket endpoint."""

    def __init__(self, node_id: int, host: str, port: int, log: LogCallback | None = None) -> None:
        self.node_id = node_id
        self.host = host
        self.port = port
        self.log = log
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)

    async def stop(self) -> None:
        if self.server is None:
            return
        self.server.close()
        await self.server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=4.0)
            if not raw:
                return
            payload = json.loads(raw.decode("utf-8"))
            if payload.get("type") != "heartbeat":
                return

            now = time.perf_counter()
            ack = {
                "type": "heartbeat_ack",
                "src": self.node_id,
                "dst": payload.get("src"),
                "seq": payload.get("seq"),
                "server_received_perf": now,
                "server_wall_time": datetime.now().isoformat(timespec="milliseconds"),
            }
            writer.write((json.dumps(ack, separators=(",", ":")) + "\n").encode("utf-8"))
            await writer.drain()

            if self.log is not None and payload.get("seq", 0) <= 3:
                self.log(
                    "REAL_NODE_RECEIVE "
                    f"node=PV{self.node_id} "
                    f"from={payload.get('src')} seq={payload.get('seq')} "
                    f"wall={ack['server_wall_time']}"
                )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


class RollingProbeStats:
    def __init__(self, maxlen: int = 12, loss_denominator_floor: int = 20) -> None:
        self.maxlen = maxlen
        self.loss_denominator_floor = loss_denominator_floor
        self._items: Deque[ProbeOutcome] = deque(maxlen=maxlen)

    def add(self, outcome: ProbeOutcome) -> None:
        self._items.append(outcome)

    def metric(
        self,
        src: int,
        dst: int,
        elapsed_s: float,
        availability_loss_threshold: float,
        availability_delay_threshold_ms: float,
    ) -> LinkMetric:
        if not self._items:
            return LinkMetric(src, dst, 0.0, 0.0, True)

        denominator = max(len(self._items), self.loss_denominator_floor)
        loss_rate = sum(1 for item in self._items if not item.ok) / denominator
        successful = [item.rtt_ms for item in self._items if item.ok]
        delay_ms = mean(successful) if successful else max(item.rtt_ms for item in self._items)
        available = loss_rate < availability_loss_threshold and delay_ms < availability_delay_threshold_ms
        return LinkMetric(src, dst, delay_ms, loss_rate, available)


class ToxiproxyMeasuredNetwork:
    """Run real node sockets, route probes through Toxiproxy, and measure QoS."""

    def __init__(
        self,
        project_root: Path,
        endpoints: Iterable[ProxyEndpoint],
        host: str = "127.0.0.1",
        node_base_port: int = 19100,
        api_url: str = "http://127.0.0.1:8474",
        probe_history_size: int = 12,
        availability_loss_threshold: float = 0.35,
        availability_delay_threshold_ms: float = 320.0,
    ) -> None:
        self.project_root = project_root
        self.host = host
        self.node_base_port = node_base_port
        self.endpoints = list(endpoints)
        self.api = ToxiproxyHttpClient(api_url)
        self.availability_loss_threshold = availability_loss_threshold
        self.availability_delay_threshold_ms = availability_delay_threshold_ms
        self.nodes = [
            VppNodeServer(node_id, host, node_base_port + node_id, self._log_limited_event)
            for node_id in NODE_IDS
        ]
        self.stats = {
            endpoint.key: RollingProbeStats(maxlen=probe_history_size)
            for endpoint in self.endpoints
        }
        self.seq = 0
        self.evidence_events: List[str] = []
        self._toxic_update_events = 0
        self.log: LogCallback | None = None

    async def start(self, log: LogCallback | None = None) -> None:
        self.log = log
        for node in self.nodes:
            await node.start()

        existing = self.api.list_proxies()
        for name in list(existing):
            if name.startswith("vpp_"):
                self.api.delete_proxy(name)

        for endpoint in self.endpoints:
            self.api.create_proxy(endpoint)

        if self.log is not None:
            self.log(
                "TOXIPROXY_NETWORK_READY "
                f"nodes={len(self.nodes)} proxies={len(self.endpoints)} "
                f"api={self.api.api_url}"
            )

    async def stop(self) -> None:
        for endpoint in self.endpoints:
            try:
                self.api.delete_proxy(endpoint.name)
            except Exception:
                pass
        await asyncio.gather(*(node.stop() for node in self.nodes), return_exceptions=True)

    async def apply_and_measure(self, elapsed_s: float, desired: QualitySnapshot) -> QualitySnapshot:
        for endpoint in self.endpoints:
            metric = desired.links[endpoint.key]
            self.api.configure_link(endpoint, metric.delay_ms, metric.loss_rate)
            if metric.delay_ms >= 500.0 or metric.loss_rate >= 0.50:
                self._record_toxic_update(endpoint, metric, elapsed_s)

        outcomes = await asyncio.gather(
            *(self._probe(endpoint, elapsed_s, desired.links[endpoint.key]) for endpoint in self.endpoints),
            return_exceptions=False,
        )
        for outcome in outcomes:
            self.stats[outcome.link_key].add(outcome)

        metrics: Dict[str, LinkMetric] = {}
        for endpoint in self.endpoints:
            metrics[endpoint.key] = self.stats[endpoint.key].metric(
                endpoint.src,
                endpoint.dst,
                elapsed_s,
                self.availability_loss_threshold,
                self.availability_delay_threshold_ms,
            )

        average_delay = sum(item.delay_ms for item in metrics.values()) / max(len(metrics), 1)
        max_loss = max((item.loss_rate for item in metrics.values()), default=0.0)
        return QualitySnapshot(elapsed_s, metrics, average_delay, max_loss)

    def diagnostic_lines(self) -> List[str]:
        lines = [
            "TOXIPROXY_REAL_NETWORK enabled=true",
            f"TOXIPROXY_PACKET_LOSS_MODE {'native_packet_loss' if self.api.native_packet_loss_supported else 'probabilistic_timeout_fallback'}",
            f"TOXIPROXY_PROXY_COUNT {len(self.endpoints)}",
        ]
        try:
            proxies = self.api.list_proxies()
            for endpoint in self.endpoints[:4]:
                proxy = proxies.get(endpoint.name, {})
                toxic_names = [
                    f"{toxic.get('name')}:{toxic.get('type')}:{toxic.get('stream')}:{toxic.get('toxicity')}"
                    for toxic in proxy.get("toxics", [])
                ]
                lines.append(
                    f"  proxy {endpoint.name} listen={endpoint.listen} upstream={endpoint.upstream} "
                    f"toxics={toxic_names}"
                )
        except Exception as exc:
            lines.append(f"TOXIPROXY_PROXY_QUERY_FAILED {exc}")

        lines.append("REAL_NETWORK_EVIDENCE")
        normal_events = [event for event in self.evidence_events if "REAL_PROBE_ACK" in event][:8]
        timeout_events = [
            event
            for event in self.evidence_events
            if "REAL_PROBE_TIMEOUT" in event and any(token in event for token in ("configured_loss=0.9", "configured_loss=0.8", "configured_loss=0.7", "configured_loss=0.6", "configured_loss=0.5"))
        ][:10]
        if len(timeout_events) < 10:
            timeout_events.extend(
                event
                for event in self.evidence_events
                if "REAL_PROBE_TIMEOUT" in event and event not in timeout_events
            )
            timeout_events = timeout_events[:10]
        receive_events = [event for event in self.evidence_events if "REAL_NODE_RECEIVE" in event][:4]
        toxic_events = [event for event in self.evidence_events if "TOXIPROXY_TOXIC_APPLIED" in event][:8]
        selected = toxic_events + receive_events + normal_events + timeout_events
        if not selected:
            selected = self.evidence_events[:24]
        lines.extend(f"  {event}" for event in selected[:24])
        return lines

    async def _probe(self, endpoint: ProxyEndpoint, elapsed_s: float, desired: LinkMetric) -> ProbeOutcome:
        self.seq += 1
        seq = self.seq
        timeout_s = min(max(desired.delay_ms / 1000.0 + 0.65, 0.65), 1.8)
        payload = {
            "type": "heartbeat",
            "src": endpoint.src,
            "dst": endpoint.dst,
            "seq": seq,
            "elapsed_s": elapsed_s,
            "client_wall_time": datetime.now().isoformat(timespec="milliseconds"),
        }

        start_perf = time.perf_counter()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(endpoint.listen_host, endpoint.listen_port),
                timeout=0.6,
            )
            writer.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=timeout_s)
            rtt_ms = (time.perf_counter() - start_perf) * 1000.0
            writer.close()
            await writer.wait_closed()

            if not raw:
                raise TimeoutError("connection closed before ack")
            ack = json.loads(raw.decode("utf-8"))
            if ack.get("seq") != seq:
                raise TimeoutError(f"unexpected ack seq={ack.get('seq')}")

            outcome = ProbeOutcome(elapsed_s, endpoint.key, seq, True, rtt_ms, desired.delay_ms, desired.loss_rate)
            self._record_evidence(
                "REAL_PROBE_ACK "
                f"wall={datetime.now().isoformat(timespec='milliseconds')} "
                f"link={endpoint.key} seq={seq} "
                f"path=Node{endpoint.src}->Toxiproxy({endpoint.listen})->Node{endpoint.dst} "
                f"configured_delay={desired.delay_ms:.1f}ms configured_loss={desired.loss_rate:.3f} "
                f"measured_rtt={rtt_ms:.1f}ms"
            )
            return outcome
        except Exception as exc:
            rtt_ms = (time.perf_counter() - start_perf) * 1000.0
            outcome = ProbeOutcome(
                elapsed_s,
                endpoint.key,
                seq,
                False,
                max(rtt_ms, timeout_s * 1000.0),
                desired.delay_ms,
                desired.loss_rate,
                str(exc),
            )
            self._record_evidence(
                "REAL_PROBE_TIMEOUT "
                f"wall={datetime.now().isoformat(timespec='milliseconds')} "
                f"link={endpoint.key} seq={seq} "
                f"path=Node{endpoint.src}->Toxiproxy({endpoint.listen})->Node{endpoint.dst} "
                f"configured_delay={desired.delay_ms:.1f}ms configured_loss={desired.loss_rate:.3f} "
                f"timeout_after={timeout_s * 1000.0:.1f}ms error={type(exc).__name__}"
            )
            return outcome

    def _record_evidence(self, event: str) -> None:
        if len(self.evidence_events) < 500:
            self.evidence_events.append(event)
        if self.log is not None and len(self.evidence_events) <= 24:
            self.log(event)

    def _log_limited_event(self, event: str) -> None:
        if len(self.evidence_events) < 12:
            self.evidence_events.append(event)
            if self.log is not None:
                self.log(event)

    def _record_toxic_update(self, endpoint: ProxyEndpoint, metric: LinkMetric, elapsed_s: float) -> None:
        if self._toxic_update_events >= 20:
            return
        try:
            proxy = self.api.get_proxy(endpoint.name)
            toxic_summary = [
                {
                    "name": toxic.get("name"),
                    "type": toxic.get("type"),
                    "stream": toxic.get("stream"),
                    "toxicity": toxic.get("toxicity"),
                    "attributes": toxic.get("attributes"),
                }
                for toxic in proxy.get("toxics", [])
            ]
        except Exception as exc:
            toxic_summary = [{"error": str(exc)}]

        self._toxic_update_events += 1
        self._record_evidence(
            "TOXIPROXY_TOXIC_APPLIED "
            f"elapsed={elapsed_s:.1f}s link={endpoint.key} proxy={endpoint.name} "
            f"configured_delay={metric.delay_ms:.1f}ms configured_loss={metric.loss_rate:.3f} "
            f"api_toxics={toxic_summary}"
        )


class ToxiproxyLinkQualitySource:
    """Gilbert-Elliott control plane + Toxiproxy real data-plane measurement."""

    def __init__(
        self,
        project_root: Path,
        cycle_s: float = 120.0,
        links: Iterable[Tuple[int, int]] = ALL_LINKS,
        host: str = "127.0.0.1",
        api_port: int = 8474,
        force_bad_link: str | None = None,
        force_bad_start_s: float = 35.0,
        force_bad_duration_s: float = 12.0,
    ) -> None:
        self.project_root = project_root
        self.model = LinkQualitySimulator(cycle_s=cycle_s)
        self.server = ToxiproxyServerProcess(project_root, host=host, port=api_port)
        self.endpoints = build_proxy_endpoints(links=links, host=host)
        self.network = ToxiproxyMeasuredNetwork(
            project_root,
            endpoints=self.endpoints,
            host=host,
            api_url=f"http://{host}:{api_port}",
        )
        self.force_bad_link = force_bad_link
        self.force_bad_start_s = force_bad_start_s
        self.force_bad_end_s = force_bad_start_s + force_bad_duration_s
        self.version = "unknown"
        self.log: LogCallback | None = None

    async def start(self, log: LogCallback | None = None) -> None:
        self.log = log
        self.version = self.server.ensure_running()
        if self.log is not None:
            self.log(f"TOXIPROXY_SERVER_STATUS running version={self.version} api={self.server.api_url}")
        await self.network.start(log)

    async def stop(self) -> None:
        await self.network.stop()
        self.server.stop_if_owned()

    async def sample(self, elapsed_s: float) -> QualitySnapshot:
        desired = self.model.sample(elapsed_s)
        desired = self._apply_manual_bad_override(desired)
        return await self.network.apply_and_measure(elapsed_s, desired)

    def diagnostic_lines(self) -> List[str]:
        lines = [
            "LINK_MODEL Gilbert-Elliott controls Toxiproxy toxics; telemetry uses measured TCP probes",
            *self.model.diagnostic_lines(),
            *self.network.diagnostic_lines(),
        ]
        return lines

    def _apply_manual_bad_override(self, snapshot: QualitySnapshot) -> QualitySnapshot:
        if not self.force_bad_link:
            return snapshot
        if not (self.force_bad_start_s <= snapshot.elapsed_s <= self.force_bad_end_s):
            return snapshot
        metric = snapshot.links.get(self.force_bad_link)
        if metric is None:
            return snapshot

        links = dict(snapshot.links)
        links[self.force_bad_link] = LinkMetric(
            metric.src,
            metric.dst,
            delay_ms=max(metric.delay_ms, 720.0),
            loss_rate=max(metric.loss_rate, 0.90),
            available=False,
        )
        average_delay = sum(item.delay_ms for item in links.values()) / len(links)
        max_loss = max(item.loss_rate for item in links.values())
        if self.log is not None:
            self.log(
                "TOXIPROXY_MANUAL_BAD_LINK "
                f"link={self.force_bad_link} elapsed={snapshot.elapsed_s:.1f}s "
                f"delay={links[self.force_bad_link].delay_ms:.1f}ms "
                f"loss={links[self.force_bad_link].loss_rate:.3f}"
            )
        return QualitySnapshot(snapshot.elapsed_s, links, average_delay, max_loss)
