import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import agent_board as ab
import fixture

with open(os.path.join(HERE, "upstream_expected.json")) as f:
    EXPECTED = json.load(f)


class Board(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = fixture.build(cls.tmp.name)
        cls.rows = ab.board(cls.paths["projects"], cls.paths["codex"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_same_rows_and_order_as_upstream(self):
        self.assertEqual([r["id"] for r in self.rows], EXPECTED["order"])
        for r in self.rows:
            with self.subTest(r["id"]):
                self.assertEqual({k: r[k] for k in ("title", "state", "tool", "subTotal", "source", "tokens")}, EXPECTED["rows"][r["id"]])

    def test_streamed_message_counted_once(self):
        row = next(r for r in self.rows if r["id"].startswith("3333"))
        self.assertEqual(row["tokens"], 620)

    def test_old_sessions_left_out(self):
        rows = ab.board(self.paths["projects"], self.paths["codex"], hours=1)
        self.assertNotIn("55555555-5555-4555-8555-555555555555", [r["id"] for r in rows])

    def test_cli_json_and_table(self):
        cmd = [sys.executable, os.path.join(ROOT, "agent_board.py"), "--claude", self.paths["projects"], "--codex", self.paths["codex"]]
        out = subprocess.run(cmd + ["--json"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        self.assertEqual(len(json.loads(out)), 8)
        table = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True).stdout
        self.assertIn("blocked", table)
        self.assertIn("Refactor cart", table)


if __name__ == "__main__":
    unittest.main()
