"""Check the published role rules against real exported node metrics."""

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.config import THRESHOLDS as T  # noqa: E402


EXPORT = ROOT / "outputs" / "nodes_roles.csv"
EXPECTED_ROLES = {
    "coordinator", "distributor", "consolidator", "transit", "terminal", "peripheral"
}
RULE_TO_ROLE = {
    "C1": "coordinator", "C2": "coordinator", "D1": "distributor",
    "K1": "consolidator", "K2": "consolidator", "T1": "transit",
    "T2": "transit", "E1": "terminal", "P-trunc": "peripheral",
    "P-leaf": "peripheral", "P-seed": "peripheral",
    "P-orphan": "peripheral", "P-other": "peripheral",
}


class RoleRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = pd.read_csv(EXPORT, dtype={"gid": "int64"})
        cls.hub_cut = cls.nodes.betweenness.quantile(T["coordinator_hub_btw_pct"])
        cls.bridge_cut = cls.nodes.betweenness.quantile(T["coordinator_betweenness_pct"])

    @classmethod
    def _flags(cls, node):
        hub = (node.in_deg >= T["coordinator_hub_min"]
               and node.out_deg >= T["coordinator_hub_min"]
               and node.betweenness >= cls.hub_cut)
        bridge = (node.in_deg >= T["coordinator_min_in"]
                  and node.out_deg >= T["coordinator_min_out"]
                  and node.betweenness >= cls.bridge_cut
                  and node.seeds_2hop >= T["coordinator_min_seeds_2hop"])
        distributor = (node.out_deg >= T["distributor_min_receivers"]
                       and node.out_deg >= T["distributor_fanout_ratio"] * max(node.in_deg, 1))
        consolidator_many = node.in_deg >= T["consolidator_min_payers"]
        consolidator_seed = (node.in_deg >= T["consolidator_min_payers_seed"]
                             and node.seed_payers >= T["consolidator_min_seed_payers"])
        has_flow = (not node.is_seed and node.in_deg > 0 and node.out_deg > 0
                    and pd.notna(node.pass_through))
        transit_balanced = (has_flow and T["transit_pass_min"] <= node.pass_through
                            <= T["transit_pass_max"])
        transit_fast = (has_flow and pd.notna(node.fast_share)
                        and node.fast_share >= T["transit_fast_share"]
                        and T["transit_pass_min_fast"] <= node.pass_through
                        <= T["transit_pass_max_fast"])
        leaf = node.depth < 4 and node.out_deg == 0 and node.in_deg > 0
        terminal = (leaf and (node.in_kzt >= T["terminal_min_in_kzt"]
                              or node.in_deg >= T["terminal_min_payers"]))
        return locals()

    def test_real_examples_per_rule(self):
        counts = self.nodes.rule.value_counts()
        self.assertEqual(set(counts.index), set(RULE_TO_ROLE))
        # Test every real C2 bridge; the current export has one.
        self.assertGreaterEqual(int(counts["C2"]), 1, "C2: no real bridge to check")
        for rule, expected_role in RULE_TO_ROLE.items():
            if rule == "C2":
                examples = self.nodes.loc[self.nodes.rule == rule].sort_values("gid")
            else:
                self.assertGreaterEqual(int(counts[rule]), 2, f"{rule}: fewer than 2 real nodes")
                examples = self.nodes.loc[self.nodes.rule == rule].sort_values("gid").head(2)
            for node in examples.itertuples(index=False):
                with self.subTest(rule=rule, gid=node.gid):
                    self.assertEqual(node.role, expected_role)
                    f = self._flags(node)
                    if rule == "C1":
                        self.assertFalse(node.truncated)
                        self.assertTrue(f["hub"])
                    elif rule == "C2":
                        self.assertFalse(node.truncated)
                        self.assertFalse(f["hub"])
                        self.assertTrue(f["bridge"])
                    elif rule == "D1":
                        self.assertTrue(f["distributor"])
                    elif rule == "K1":
                        self.assertTrue(f["consolidator_many"])
                    elif rule == "K2":
                        self.assertFalse(f["consolidator_many"])
                        self.assertTrue(f["consolidator_seed"])
                    elif rule == "T1":
                        self.assertTrue(f["transit_balanced"])
                    elif rule == "T2":
                        self.assertFalse(f["transit_balanced"])
                        self.assertTrue(f["transit_fast"])
                    elif rule == "E1":
                        self.assertFalse(node.truncated)
                        self.assertTrue(f["terminal"])
                    elif rule == "P-trunc":
                        self.assertEqual(node.depth, 4)
                        self.assertEqual(node.out_deg, 0)
                        self.assertTrue(node.truncated)
                    elif rule == "P-orphan":
                        self.assertEqual((node.in_deg, node.out_deg), (0, 0))
                    elif rule == "P-seed":
                        self.assertTrue(node.is_seed)
                        self.assertFalse(node.truncated)
                        self.assertNotEqual((node.in_deg, node.out_deg), (0, 0))
                    elif rule == "P-leaf":
                        self.assertFalse(node.truncated)
                        self.assertFalse(node.is_seed)
                        self.assertTrue(f["leaf"])
                        self.assertFalse(f["terminal"])
                    elif rule == "P-other":
                        self.assertFalse(node.truncated)
                        self.assertFalse(node.is_seed)
                        self.assertFalse(f["leaf"])
                        self.assertFalse(f["hub"] or f["bridge"] or f["distributor"]
                                         or f["consolidator_many"] or f["consolidator_seed"]
                                         or f["transit_balanced"] or f["transit_fast"])

    def test_global_safety_and_coverage(self):
        self.assertEqual(len(self.nodes), 2248)
        self.assertEqual(set(self.nodes.role), EXPECTED_ROLES)
        self.assertEqual(self.nodes.groupby("role").size().sum(), 2248)
        self.assertTrue((self.nodes.loc[self.nodes.truncated, "role"] != "terminal").all())
        self.assertTrue((self.nodes.loc[self.nodes.is_seed, "role"] != "transit").all())


if __name__ == "__main__":
    unittest.main()
