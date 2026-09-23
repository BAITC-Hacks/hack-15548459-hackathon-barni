import pandas as pd
import unittest

from ui.aml.data import money, short_why
from ui.aml.graph import select_graph_nodes, visible_graph_edges


def _sample():
    nodes = pd.DataFrame({
        "gid": ["100000000000000001", "100000000000000002", "100000000000000003"],
        "role": ["coordinator", "transit", "terminal"],
        "cluster_id": [1, 2, 2],
        "priority_score": [0.9, 0.8, 0.7],
        "is_seed": [True, False, False],
    })
    edges = pd.DataFrame({
        "src": ["100000000000000001", "100000000000000002"],
        "dst": ["100000000000000002", "100000000000000003"],
        "sum_kzt": [1_234_567, 2_000],
        "n_tx": [2, 1],
    })
    return nodes, edges


class UIDetailsTests(unittest.TestCase):
    def test_selected_node_survives_role_filter_and_cluster_limits_neighbors(self):
        nodes, edges = _sample()
        shown, eligible, role_override, cluster_override = select_graph_nodes(
            nodes, edges, "100000000000000001", ["transit"], 2, 2,
        )
        self.assertEqual(shown["gid"].tolist(), ["100000000000000001", "100000000000000002"])
        self.assertEqual(eligible, 2)
        self.assertTrue(role_override and cluster_override)
        self.assertEqual(len(visible_graph_edges(shown, edges)), 1)

    def test_cap_and_tie_order_are_deterministic_and_selected_is_kept(self):
        nodes = pd.DataFrame({
            "gid": [f"{i:018d}" for i in range(305)],
            "role": ["transit"] * 304 + ["coordinator"],
            "priority_score": [0.5] * 305,
        })
        selected = "000000000000000304"
        edges = pd.DataFrame({"src": [selected] * 304, "dst": nodes.loc[nodes["gid"] != selected, "gid"].tolist()})
        first, eligible, override, _ = select_graph_nodes(nodes, edges, selected, ["transit"], None, 1, cap=3)
        second, _, _, _ = select_graph_nodes(nodes.iloc[::-1], edges, selected, ["transit"], None, 1, cap=3)
        self.assertEqual(eligible, 305)
        self.assertTrue(override)
        self.assertEqual(first["gid"].tolist(), second["gid"].tolist())
        self.assertEqual(first.iloc[0]["gid"], selected)

    def test_ids_and_money_formatting_handle_large_and_missing_values(self):
        nodes, edges = _sample()
        shown, *_ = select_graph_nodes(nodes, edges, None, ["coordinator", "transit", "terminal"], None, 0)
        self.assertEqual(shown.iloc[0]["gid"], "100000000000000001")
        self.assertEqual(money(1_234_567), "1,2 млн ₸")
        self.assertEqual(money(1_234_567_890), "1,2 млрд ₸")
        self.assertEqual(money(float("inf")), "—")
        self.assertEqual(money(pd.NA), "—")
        self.assertEqual(short_why(pd.NA), "—")
        self.assertEqual(short_why(float("nan")), "—")
