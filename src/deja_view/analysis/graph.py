"""
Activity graph for Deja View.

Builds and maintains a networkx graph representing relationships
between files, repositories, URLs, commands, and processes.
"""

import logging
import pickle
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

import networkx as nx

from deja_view.config import get_config
from deja_view.models import ActivityWindow, Event, EventType


class ActivityGraph:
    """
    Graph representation of activity relationships.
    
    Nodes represent entities (files, repos, URLs, commands, processes).
    Edges represent co-occurrence within activity windows.
    """
    
    # Node type prefixes
    NODE_TYPES = {
        "file": "file:",
        "repo": "repo:",
        "url": "url:",
        "command": "cmd:",
        "process": "proc:",
        "domain": "domain:",
    }
    
    def __init__(self, graph_path: Optional[Path] = None):
        """
        Initialize the activity graph.
        
        Args:
            graph_path: Path to persist the graph.
                       Uses config default if not provided.
        """
        config = get_config()
        self.graph_path = graph_path or config.graph_path
        self.logger = logging.getLogger("deja.analysis.graph")
        self._graph = nx.Graph()
        
        # Ensure parent directory exists
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
    
    @property
    def graph(self) -> nx.Graph:
        """Get the underlying networkx graph.
        
        Returns:
            The underlying networkx Graph instance.
        """
        return self._graph
    
    def _get_node_id(self, node_type: str, value: str) -> str:
        """Generate a node ID from type and value.
        
        Args:
            node_type: The type of node (e.g., 'file', 'repo', 'url').
            value: The value to use for the node ID.
            
        Returns:
            A formatted node ID string with type prefix.
        """
        prefix = self.NODE_TYPES.get(node_type, f"{node_type}:")
        # Truncate long values
        if len(value) > 200:
            value = value[:200]
        return f"{prefix}{value}"
    
    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract domain from a URL.
        
        Args:
            url: The URL to extract the domain from.
            
        Returns:
            The domain (netloc) portion of the URL, or None if extraction fails.
        """
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except Exception:
            return None
    
    def add_event(self, event: Event) -> None:
        """Add a single event to the graph.
        
        Creates nodes for entities in the event and updates
        node attributes.
        
        Args:
            event: The Event instance to add to the graph.
        """
        # Determine node type and ID based on event
        node_id = None
        node_attrs: Dict[str, Any] = {
            "last_seen": event.timestamp.isoformat(),
            "event_count": 1,
        }
        
        if event.event_type in {
            EventType.FILE_CREATE, EventType.FILE_MODIFY,
            EventType.FILE_DELETE, EventType.FILE_MOVE
        }:
            node_id = self._get_node_id("file", event.subject)
            node_attrs["type"] = "file"
            node_attrs["path"] = event.subject
            
        elif event.event_type in {
            EventType.GIT_COMMIT, EventType.GIT_BRANCH_SWITCH
        }:
            if event.repository:
                node_id = self._get_node_id("repo", event.repository)
                node_attrs["type"] = "repo"
                node_attrs["path"] = event.repository
                
        elif event.event_type == EventType.BROWSER_VISIT:
            if event.url:
                node_id = self._get_node_id("url", event.url)
                node_attrs["type"] = "url"
                node_attrs["url"] = event.url
                node_attrs["title"] = event.title
                
                # Also add domain node
                domain = self._extract_domain(event.url)
                if domain:
                    domain_id = self._get_node_id("domain", domain)
                    if domain_id in self._graph:
                        self._graph.nodes[domain_id]["event_count"] = \
                            self._graph.nodes[domain_id].get("event_count", 0) + 1
                    else:
                        self._graph.add_node(domain_id, type="domain", domain=domain, event_count=1)
                    
        elif event.event_type == EventType.SHELL_COMMAND:
            # Use first word of command
            cmd_base = event.subject.split()[0] if event.subject else ""
            if cmd_base:
                node_id = self._get_node_id("command", cmd_base)
                node_attrs["type"] = "command"
                node_attrs["command"] = cmd_base
                
        elif event.event_type in {
            EventType.PROCESS_START, EventType.PROCESS_ACTIVE
        }:
            if event.process_name:
                node_id = self._get_node_id("process", event.process_name)
                node_attrs["type"] = "process"
                node_attrs["name"] = event.process_name
        
        if node_id:
            if node_id in self._graph:
                # Update existing node
                self._graph.nodes[node_id]["event_count"] = \
                    self._graph.nodes[node_id].get("event_count", 0) + 1
                self._graph.nodes[node_id]["last_seen"] = event.timestamp.isoformat()
            else:
                self._graph.add_node(node_id, **node_attrs)
    
    def add_window(self, window: ActivityWindow) -> None:
        """Add events from an activity window and create edges.
        
        Events in the same window are considered co-occurring,
        so edges are created between their corresponding nodes.
        
        Args:
            window: The ActivityWindow instance containing events to add.
        """
        # First add all events
        for event in window.events:
            self.add_event(event)
        
        # Collect node IDs from this window
        node_ids: Set[str] = set()
        
        for event in window.events:
            if event.event_type in {
                EventType.FILE_CREATE, EventType.FILE_MODIFY,
                EventType.FILE_DELETE, EventType.FILE_MOVE
            }:
                node_ids.add(self._get_node_id("file", event.subject))
                
            elif event.event_type in {EventType.GIT_COMMIT, EventType.GIT_BRANCH_SWITCH}:
                if event.repository:
                    node_ids.add(self._get_node_id("repo", event.repository))
                    
            elif event.event_type == EventType.BROWSER_VISIT and event.url:
                domain = self._extract_domain(event.url)
                if domain:
                    node_ids.add(self._get_node_id("domain", domain))
                    
            elif event.event_type == EventType.SHELL_COMMAND:
                cmd_base = event.subject.split()[0] if event.subject else ""
                if cmd_base:
                    node_ids.add(self._get_node_id("command", cmd_base))
                    
            elif event.event_type in {EventType.PROCESS_START, EventType.PROCESS_ACTIVE}:
                if event.process_name:
                    node_ids.add(self._get_node_id("process", event.process_name))
        
        # Create edges between all pairs
        node_list = list(node_ids)
        for i in range(len(node_list)):
            for j in range(i + 1, len(node_list)):
                if self._graph.has_edge(node_list[i], node_list[j]):
                    self._graph[node_list[i]][node_list[j]]["weight"] += 1
                else:
                    self._graph.add_edge(node_list[i], node_list[j], weight=1)
    
    def get_related_nodes(
        self,
        node_id: str,
        max_depth: int = 2,
        min_weight: int = 1
    ) -> List[Tuple[str, int]]:
        """Get nodes related to a given node.
        
        Traverses the graph up to max_depth edges away from the given node,
        collecting nodes that meet the minimum weight threshold.
        
        Args:
            node_id: The node ID to find relations for.
            max_depth: Maximum edge distance to search. Defaults to 2.
            min_weight: Minimum edge weight to consider. Defaults to 1.
            
        Returns:
            A list of (node_id, total_weight) tuples sorted by weight descending.
        """
        if node_id not in self._graph:
            return []
        
        related: Dict[str, int] = {}
        visited = {node_id}
        current = {node_id}
        
        for depth in range(max_depth):
            next_nodes = set()
            for node in current:
                for neighbor in self._graph.neighbors(node):
                    if neighbor in visited:
                        continue
                    weight = self._graph[node][neighbor].get("weight", 1)
                    if weight >= min_weight:
                        related[neighbor] = related.get(neighbor, 0) + weight
                        next_nodes.add(neighbor)
                        visited.add(neighbor)
            current = next_nodes
        
        return sorted(related.items(), key=lambda x: x[1], reverse=True)
    
    def find_node(self, query: str) -> List[str]:
        """Find nodes matching a query string.
        
        Performs a case-insensitive substring search across all node IDs.
        
        Args:
            query: The string to search for in node IDs.
            
        Returns:
            A list of node IDs that contain the query string.
        """
        query_lower = query.lower()
        matches = []
        
        for node_id in self._graph.nodes():
            if query_lower in node_id.lower():
                matches.append(node_id)
        
        return matches
    
    def get_node_info(self, node_id: str) -> Optional[Dict]:
        """Get information about a specific node.
        
        Args:
            node_id: The node ID to look up.
            
        Returns:
            A dictionary containing the node's attributes including 'id' and
            'degree', or None if the node does not exist.
        """
        if node_id in self._graph:
            info = dict(self._graph.nodes[node_id])
            info["id"] = node_id
            info["degree"] = self._graph.degree(node_id)
            return info
        return None
    
    def get_most_connected(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get the most connected nodes.
        
        Args:
            limit: Maximum number of nodes to return. Defaults to 10.
            
        Returns:
            A list of (node_id, degree) tuples sorted by degree descending.
        """
        degrees = [(node, self._graph.degree(node)) for node in self._graph.nodes()]
        return sorted(degrees, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_clusters(self) -> List[Set[str]]:
        """Get connected components (clusters) in the graph.
        
        Returns:
            A list of sets, where each set contains the node IDs of a
            connected component.
        """
        return [set(c) for c in nx.connected_components(self._graph)]
    
    def get_statistics(self) -> Dict:
        """Get graph statistics.
        
        Returns:
            A dictionary containing graph statistics including 'nodes', 'edges',
            'clusters', 'density', and 'node_types'.
        """
        if self._graph.number_of_nodes() == 0:
            return {"nodes": 0, "edges": 0}
        
        type_counts: Dict[str, int] = defaultdict(int)
        for node in self._graph.nodes():
            node_type = self._graph.nodes[node].get("type", "unknown")
            type_counts[node_type] += 1
        
        return {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "clusters": nx.number_connected_components(self._graph),
            "density": nx.density(self._graph),
            "node_types": dict(type_counts),
        }
    
    def save(self) -> None:
        """Save the graph to disk.
        
        Persists the graph to the configured graph_path using pickle
        serialization.
        """
        with open(self.graph_path, "wb") as f:
            pickle.dump(self._graph, f)
        self.logger.info(f"Graph saved to {self.graph_path}")
    
    def load(self) -> bool:
        """Load the graph from disk.
        
        Attempts to load a previously saved graph from the configured
        graph_path using pickle deserialization.
        
        Returns:
            True if the graph was loaded successfully, False otherwise.
        """
        if not self.graph_path.exists():
            self.logger.info("No existing graph found")
            return False
        
        try:
            with open(self.graph_path, "rb") as f:
                self._graph = pickle.load(f)
            self.logger.info(f"Graph loaded from {self.graph_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load graph: {e}")
            return False
    
    def clear(self) -> None:
        """Clear the graph.
        
        Removes all nodes and edges from the graph.
        """
        self._graph.clear()
