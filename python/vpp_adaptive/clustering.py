from __future__ import annotations

from typing import Dict, Iterable, List, Set, Tuple

from .models import QualitySnapshot


class ConnectivityClusterer:
    """Compute connected components from topology and usable links."""

    def __init__(
        self,
        nodes: Iterable[int] = range(1, 6),
        topology_edges: Iterable[Tuple[int, int]] | None = None,
    ) -> None:
        self.nodes = list(nodes)
        self.topology_edges = {
            tuple(sorted(edge))
            for edge in (
                topology_edges
                if topology_edges is not None
                else [(1, 2), (1, 4), (2, 3), (3, 4), (3, 5), (4, 5)]
            )
        }

    def connected_components(self, snapshot: QualitySnapshot) -> List[List[int]]:
        graph: Dict[int, Set[int]] = {node: set() for node in self.nodes}
        for edge in self.topology_edges:
            key = f"{edge[0]}-{edge[1]}"
            metric = snapshot.links.get(key)
            if metric is not None and metric.available:
                graph[edge[0]].add(edge[1])
                graph[edge[1]].add(edge[0])

        components: List[List[int]] = []
        seen: Set[int] = set()
        for node in self.nodes:
            if node in seen:
                continue
            stack = [node]
            seen.add(node)
            component: List[int] = []
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in graph[current]:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        stack.append(neighbor)
            components.append(sorted(component))
        return sorted(components, key=lambda item: (item[0], len(item)))
