from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import requests

from .security import MASTER_ACTOR, ZeroTrustSecurityManager

try:  # Imported to ensure the requested Python client package is present.
    import toxiproxy as toxiproxy_python_client  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover - direct HTTP API remains the runtime path.
    toxiproxy_python_client = None


NODE_IDS = tuple(range(1, 6))
ALL_LINKS = tuple(combinations(NODE_IDS, 2))
TOPOLOGY_EDGES = ((1, 2), (1, 4), (2, 3), (3, 4), (3, 5), (4, 5))


@dataclass(frozen=True)
class ProxyEndpoint:
    src: int
    dst: int
    name: str
    listen_host: str
    listen_port: int
    upstream_host: str
    upstream_port: int

    @property
    def key(self) -> str:
        return f"{self.src}-{self.dst}"

    @property
    def listen(self) -> str:
        return f"{self.listen_host}:{self.listen_port}"

    @property
    def upstream(self) -> str:
        return f"{self.upstream_host}:{self.upstream_port}"


class ToxiproxyApiError(RuntimeError):
    pass


class ToxiproxyHttpClient:
    """Thin HTTP API wrapper for the Toxiproxy management server."""

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8474",
        security: ZeroTrustSecurityManager | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "adapvpp-toxiproxy-client/1.0"})
        self.native_packet_loss_supported: bool | None = None
        self.security = security

    def version(self) -> str:
        response = self.session.get(f"{self.api_url}/version", timeout=2)
        response.raise_for_status()
        return str(response.json().get("version", "unknown"))

    def list_proxies(self) -> Dict[str, dict]:
        response = self.session.get(f"{self.api_url}/proxies", timeout=5)
        response.raise_for_status()
        return response.json()

    def get_proxy(self, name: str) -> dict:
        response = self.session.get(f"{self.api_url}/proxies/{name}", timeout=5)
        response.raise_for_status()
        return response.json()

    def delete_proxy(self, name: str, actor: str = MASTER_ACTOR) -> None:
        self._require_control(actor, "toxiproxy.delete_proxy", {"proxy": name})
        response = self.session.delete(f"{self.api_url}/proxies/{name}", timeout=5)
        if response.status_code not in {200, 204, 404}:
            raise ToxiproxyApiError(f"delete proxy {name} failed: {response.status_code} {response.text}")

    def create_proxy(self, endpoint: ProxyEndpoint, actor: str = MASTER_ACTOR) -> dict:
        self._require_control(actor, "toxiproxy.create_proxy", {"proxy": endpoint.name})
        payload = {
            "name": endpoint.name,
            "listen": endpoint.listen,
            "upstream": endpoint.upstream,
        }
        response = self.session.post(f"{self.api_url}/proxies", json=payload, timeout=5)
        if response.status_code == 409:
            self.delete_proxy(endpoint.name, actor=actor)
            response = self.session.post(f"{self.api_url}/proxies", json=payload, timeout=5)
        if response.status_code not in {200, 201}:
            raise ToxiproxyApiError(
                f"create proxy {endpoint.name} failed: {response.status_code} {response.text}"
            )
        return response.json()

    def delete_toxic(self, proxy_name: str, toxic_name: str, actor: str = MASTER_ACTOR) -> None:
        self._require_control(
            actor,
            "toxiproxy.delete_toxic",
            {"proxy": proxy_name, "toxic": toxic_name},
        )
        response = self.session.delete(
            f"{self.api_url}/proxies/{proxy_name}/toxics/{toxic_name}",
            timeout=5,
        )
        if response.status_code not in {200, 204, 404}:
            raise ToxiproxyApiError(
                f"delete toxic {proxy_name}/{toxic_name} failed: {response.status_code} {response.text}"
            )

    def replace_toxic(
        self,
        proxy_name: str,
        toxic_name: str,
        toxic_type: str,
        stream: str,
        toxicity: float,
        attributes: dict,
        actor: str = MASTER_ACTOR,
    ) -> dict:
        self._require_control(
            actor,
            "toxiproxy.replace_toxic",
            {"proxy": proxy_name, "toxic": toxic_name, "type": toxic_type},
        )
        payload = {
            "name": toxic_name,
            "type": toxic_type,
            "stream": stream,
            "toxicity": max(0.0, min(float(toxicity), 1.0)),
            "attributes": attributes,
        }
        patch_response = self.session.patch(
            f"{self.api_url}/proxies/{proxy_name}/toxics/{toxic_name}",
            json=payload,
            timeout=5,
        )
        if patch_response.status_code in {200, 204}:
            if patch_response.text:
                return patch_response.json()
            return payload
        if patch_response.status_code != 404:
            raise ToxiproxyApiError(
                f"patch toxic {proxy_name}/{toxic_name} failed: "
                f"{patch_response.status_code} {patch_response.text}"
            )

        post_response = self.session.post(
            f"{self.api_url}/proxies/{proxy_name}/toxics",
            json=payload,
            timeout=5,
        )
        if post_response.status_code not in {200, 201}:
            raise ToxiproxyApiError(
                f"create toxic {proxy_name}/{toxic_name} failed: "
                f"{post_response.status_code} {post_response.text}"
            )
        return post_response.json()

    def configure_link(
        self,
        endpoint: ProxyEndpoint,
        delay_ms: float,
        loss_rate: float,
        actor: str = MASTER_ACTOR,
    ) -> None:
        """Write real network impairment into both directions of one proxy."""

        self._require_control(
            actor,
            "toxiproxy.configure_link",
            {"link": endpoint.key, "delay_ms": delay_ms, "loss_rate": loss_rate},
        )

        one_way_latency_ms = max(0, int(round(delay_ms / 2.0)))
        jitter_ms = max(1, int(round(max(delay_ms * 0.08, 2.0) / 2.0)))

        for stream in ("downstream", "upstream"):
            self.replace_toxic(
                endpoint.name,
                f"vpp_latency_{stream}",
                "latency",
                stream,
                1.0,
                {"latency": one_way_latency_ms, "jitter": jitter_ms},
                actor=actor,
            )

        self._configure_loss(endpoint, loss_rate, actor=actor)

    def _configure_loss(self, endpoint: ProxyEndpoint, loss_rate: float, actor: str = MASTER_ACTOR) -> None:
        loss_rate = max(0.0, min(float(loss_rate), 0.98))
        if self.native_packet_loss_supported is None:
            self.native_packet_loss_supported = self._probe_packet_loss_support(endpoint.name)

        if self.native_packet_loss_supported:
            for stream in ("downstream", "upstream"):
                self.replace_toxic(
                    endpoint.name,
                    f"vpp_packet_loss_{stream}",
                    "packet_loss",
                    stream,
                    1.0,
                    {"percentage": loss_rate * 100.0},
                    actor=actor,
                )
            return

        # Toxiproxy 2.12.0 does not expose a native packet_loss toxic. Because
        # every heartbeat probe opens a fresh TCP connection, a probabilistic
        # timeout toxic with toxicity derived from the desired loss rate creates
        # real dropped/timeout probe exchanges on the data path.
        per_stream_toxicity = 1.0 - (1.0 - loss_rate) ** 0.5
        for stream in ("downstream", "upstream"):
            self.replace_toxic(
                endpoint.name,
                f"vpp_loss_timeout_{stream}",
                "timeout",
                stream,
                per_stream_toxicity,
                {"timeout": 1},
                actor=actor,
            )

    def _probe_packet_loss_support(self, proxy_name: str) -> bool:
        toxic_name = "vpp_packet_loss_capability_probe"
        payload = {
            "name": toxic_name,
            "type": "packet_loss",
            "stream": "downstream",
            "toxicity": 0.0,
            "attributes": {"percentage": 0.0},
        }
        response = self.session.post(
            f"{self.api_url}/proxies/{proxy_name}/toxics",
            json=payload,
            timeout=5,
        )
        if response.status_code in {200, 201}:
            self.delete_toxic(proxy_name, toxic_name)
            return True
        return False

    def _require_control(self, actor: str, interface: str, metadata: dict) -> None:
        if self.security is not None:
            self.security.require_control_actor(actor, interface, metadata)


class ToxiproxyServerProcess:
    """Start a local Toxiproxy server when one is not already listening."""

    def __init__(
        self,
        project_root: Path,
        host: str = "127.0.0.1",
        port: int = 8474,
    ) -> None:
        self.project_root = project_root
        self.host = host
        self.port = port
        self.api_url = f"http://{host}:{port}"
        self.client = ToxiproxyHttpClient(self.api_url)
        self.process: subprocess.Popen[str] | None = None

    def ensure_running(self) -> str:
        try:
            return self.client.version()
        except requests.RequestException:
            pass

        binary = self._server_binary()
        log_dir = self.project_root / "tools" / "toxiproxy"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout = (log_dir / "toxiproxy-server.log").open("a", encoding="utf-8")
        stderr = (log_dir / "toxiproxy-server.err.log").open("a", encoding="utf-8")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        self.process = subprocess.Popen(
            [str(binary), "-host", self.host, "-port", str(self.port)],
            cwd=str(log_dir),
            stdout=stdout,
            stderr=stderr,
            text=True,
            creationflags=creationflags,
        )

        deadline = time.monotonic() + 10.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self.client.version()
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(0.2)
        raise RuntimeError(f"Toxiproxy server did not become ready: {last_error}")

    def stop_if_owned(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def _server_binary(self) -> Path:
        exe_name = "toxiproxy-server.exe" if sys.platform == "win32" else "toxiproxy-server"
        binary = self.project_root / "tools" / "toxiproxy" / exe_name
        if binary.exists():
            return binary

        downloader = self.project_root / "tools" / "download_toxiproxy.py"
        if not downloader.exists():
            raise FileNotFoundError(f"Toxiproxy binary missing and downloader not found: {downloader}")
        subprocess.run(
            [sys.executable, str(downloader)],
            cwd=str(self.project_root),
            check=True,
        )
        if not binary.exists():
            raise FileNotFoundError(f"Toxiproxy download did not create expected binary: {binary}")
        return binary


def build_proxy_endpoints(
    links: Iterable[Tuple[int, int]] = ALL_LINKS,
    host: str = "127.0.0.1",
    node_base_port: int = 19100,
    proxy_base_port: int = 19200,
) -> List[ProxyEndpoint]:
    endpoints: List[ProxyEndpoint] = []
    for idx, edge in enumerate(sorted(tuple(sorted(link)) for link in links), start=1):
        src, dst = edge
        endpoints.append(
            ProxyEndpoint(
                src=src,
                dst=dst,
                name=f"vpp_{src}_{dst}",
                listen_host=host,
                listen_port=proxy_base_port + idx,
                upstream_host=host,
                upstream_port=node_base_port + dst,
            )
        )
    return endpoints
