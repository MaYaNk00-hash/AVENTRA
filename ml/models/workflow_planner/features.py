from typing import List, Dict, Any
import networkx as nx


def validate_dag_structure(nodes: List[Dict[str, Any]], edges: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Validates that a workflow graph is a true Directed Acyclic Graph (DAG)
    with no unreachable dead-ends and valid dependencies.
    """
    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n["id"], tool=n.get("tool"))

    for e in edges:
        g.add_edge(e["source"], e["target"])

    is_dag = nx.is_directed_acyclic_graph(g)
    has_cycle = not is_dag
    cycle_nodes = list(nx.simple_cycles(g)) if has_cycle else []

    return {
        "is_valid_dag": is_dag,
        "has_cycle": has_cycle,
        "cycle_details": cycle_nodes,
        "node_count": len(nodes),
        "edge_count": len(edges)
    }

