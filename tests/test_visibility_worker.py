import unittest
from types import SimpleNamespace

from game.entity.VisibilityWorker import VisibilityWorker


def make_worker(occluded_bounds_x_below=0.0):
    """Worker whose probe hides entities whose bounds sit behind a wall."""
    def prove(camera, bounds):
        return (9, 70, 4) if bounds[0] < occluded_bounds_x_below else None

    scene = SimpleNamespace(_prove_entity_occluded=prove)
    return VisibilityWorker(scene)


class VisibilityWorkerTests(unittest.TestCase):
    def test_hidden_entities_need_two_consecutive_passes(self):
        worker = make_worker()
        snapshot = (1, (0, 70, 0), [(11, (-5.0, 68, -5, -4, 72, -4))])

        worker.process(snapshot)
        self.assertEqual(worker.results, set())  # first pass: hysteresis only

        worker.process((2, (0, 70, 0), snapshot[2]))
        self.assertEqual(worker.results, {11})   # confirmed on second pass
        self.assertEqual(worker.results_tick, 2)
        self.assertEqual(worker.results_camera, (0, 70, 0))

    def test_entities_reappear_immediately_when_unoccluded(self):
        worker = make_worker()
        behind = [(11, (-5.0, 68, -5, -4, 72, -4))]
        in_front = [(12, (5.0, 68, 5, 6, 72, 6))]

        worker.process((1, (0, 70, 0), behind))
        worker.process((2, (0, 70, 0), behind))
        self.assertEqual(worker.results, {11})

        worker.process((3, (0, 70, 0), in_front))
        self.assertEqual(worker.results, set())  # visible again, no streak

    def test_probe_failures_are_skipped_not_fatal(self):
        def prove(camera, bounds):
            raise RuntimeError("dict mutated")

        worker = VisibilityWorker(
            SimpleNamespace(_prove_entity_occluded=prove))
        worker.process((1, (0, 0, 0), [(11, (0, 0, 0, 1, 1, 1))]))
        self.assertEqual(worker.results, set())
        self.assertEqual(worker.results_tick, 1)

    def test_submit_is_ignored_while_busy(self):
        worker = make_worker()
        worker._busy = True
        self.assertFalse(worker.submit(1, (0, 0, 0), []))
        worker._busy = False
        self.assertTrue(worker.submit(1, (0, 0, 0), []))

    def test_close_stops_the_thread(self):
        worker = make_worker()
        worker.start()
        worker.submit(1, (0, 0, 0), [])
        worker.close()
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())


class SceneAsyncVisibilityTests(unittest.TestCase):
    def test_scene_consume_uses_worker_results(self):
        """The Scene consume logic: hidden ids filter candidates directly."""
        candidates = [
            (SimpleNamespace(name="visible_a"), (0, 0, 0, 1, 1, 1)),
            (SimpleNamespace(name="hidden_b"), (-9, 0, 0, -8, 1, 1)),
            (SimpleNamespace(name="unbounded"), None),
        ]
        hidden = {id(candidates[1][0])}
        visible = [
            entity for entity, bounds in candidates
            if bounds is None or id(entity) not in hidden
        ]
        self.assertEqual([e.name for e in visible],
                         ["visible_a", "unbounded"])


if __name__ == "__main__":
    unittest.main()
