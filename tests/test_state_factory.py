import unittest

from src.workflow.state_factory import build_initial_state, default_project_name


class StateFactoryTests(unittest.TestCase):
    def test_default_project_name(self):
        self.assertEqual(default_project_name(None), "default_project")
        self.assertEqual(default_project_name("thread_12345678"), "proj_12345678")

    def test_build_initial_state_has_expected_defaults(self):
        state = build_initial_state(
            "写一个短剧",
            project_name="proj_test",
            reference_text="ref",
            reference_images=["img1"],
        )
        self.assertEqual(state["user_request"], "写一个短剧")
        self.assertEqual(state["project_name"], "proj_test")
        self.assertEqual(state["reference_text"], "ref")
        self.assertEqual(state["reference_images"], ["img1"])
        self.assertEqual(state["script_review_count"], 0)
        self.assertEqual(state["production_review_count"], 0)
        self.assertEqual(state["storyboard_review_count"], 0)
        self.assertEqual(state["current_node"], "")


if __name__ == "__main__":
    unittest.main()
