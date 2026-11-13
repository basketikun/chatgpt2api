"""Per-exit cookies must stay per exit.

Cloudflare binds its per-path scoring to the client that earned it, so a lane's cookies
are only worth anything to a caller leaving through the same egress. The solver therefore
reports them per lane, and the caller asks for its own exit by name (`/health?proxy=`)
rather than being handed a merged set it cannot use. These tests pin the two ways that
could quietly break: lanes collapsing onto one key, and a probe warming or borrowing a
lane it does not own.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOLVER_DIR = Path(__file__).resolve().parent.parent / "sentinel_solver"
if str(SOLVER_DIR) not in sys.path:
    # `app.py` imports its sibling `turnstile_result` by plain module name, the way the
    # container runs it (WORKDIR is the solver directory).
    sys.path.insert(0, str(SOLVER_DIR))

from app import SolverPage, _lane_proxy_spec  # noqa: E402
from app import _Lane  # noqa: E402


def lane_key(proxy: str) -> str:
    return SolverPage._lane_key(_lane_proxy_spec(proxy))


class LaneKeyTests(unittest.TestCase):
    def test_exits_that_share_a_host_are_different_lanes(self):
        # Residential pools route one host:port and distinguish exits by username, so
        # dropping credentials would let one exit's cookies answer for another's.
        self.assertNotEqual(
            lane_key("http://user-a:pw@exit.example:8080"),
            lane_key("http://user-b:pw@exit.example:8080"),
        )

    def test_the_default_egress_has_no_key(self):
        self.assertEqual(lane_key(""), "")
        self.assertEqual(lane_key("   "), "")

    def test_the_same_exit_written_differently_is_one_lane(self):
        self.assertEqual(lane_key("http://exit.example:8080"), lane_key("http://exit.example:8080/"))


class ExitCookieTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.solver = SolverPage()

    def add_lane(self, proxy: str, cookies: dict[str, str]):
        key = lane_key(proxy)
        lane = _Lane(self.solver, key, _lane_proxy_spec(proxy))
        lane.cookies = cookies
        self.solver._lanes[key] = lane
        return lane

    async def test_an_exit_gets_only_its_own_cookies(self):
        self.add_lane("http://exit-a:8080", {"__cf_bm": "earned-on-a"})
        self.add_lane("http://exit-b:8080", {"__cf_bm": "earned-on-b"})

        own = await self.solver.exit_status("http://exit-a:8080")
        other = await self.solver.exit_status("http://exit-b:8080")

        self.assertEqual(own["cookies"], {"__cf_bm": "earned-on-a"})
        self.assertEqual(other["cookies"], {"__cf_bm": "earned-on-b"})

    async def test_an_unwarmed_exit_is_answered_empty_not_borrowed(self):
        self.add_lane("http://exit-a:8080", {"__cf_bm": "earned-on-a"})
        status = await self.solver.exit_status("http://exit-c:8080")
        self.assertEqual(status["cookies"], {})
        self.assertFalse(status["warmed"])

    async def test_the_default_lane_is_not_handed_to_an_unnamed_caller(self):
        # The empty lane is the solver's own egress, which is not the caller's IP.
        self.add_lane("", {"__cf_bm": "solver-egress"})
        self.assertEqual((await self.solver.exit_status(""))["cookies"], {})

    async def test_a_probe_never_warms_or_creates_a_lane(self):
        await self.solver.exit_status("http://exit-d:8080")
        self.assertEqual(self.solver._lanes, {})

    async def test_a_closed_lane_stops_reporting_cookies(self):
        lane = self.add_lane("http://exit-a:8080", {"__cf_bm": "earned-on-a"})
        await lane.close()
        self.assertEqual((await self.solver.exit_status("http://exit-a:8080"))["cookies"], {})

    def test_the_general_status_does_not_merge_lanes(self):
        """Every lane's cookies are visible for inspection, but never as one set."""
        self.add_lane("http://exit-a:8080", {"__cf_bm": "earned-on-a"})
        self.solver._lanes[lane_key("")] = _Lane(self.solver, "", {})
        status = self.solver.status()
        self.assertNotIn("cookies", status)
        self.assertEqual(status["lanes"][lane_key("http://exit-a:8080")]["cookies"], {"__cf_bm": "earned-on-a"})


if __name__ == "__main__":
    unittest.main()
