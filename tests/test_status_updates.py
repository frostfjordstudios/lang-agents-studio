import unittest

from src.workflow.runtime.messaging import format_node_message
from src.workflow.runtime.status_updates import format_status_update, format_task_received


class StatusUpdateTests(unittest.TestCase):
    def test_format_status_update_basic(self):
        msg = format_status_update("proj_001", "剧本初稿完成", node_name="writer", summary="done")
        self.assertIn("项目：proj_001", msg)
        self.assertIn("状态：剧本初稿完成", msg)
        self.assertIn("节点：writer", msg)
        self.assertIn("摘要：done", msg)

    def test_format_task_received(self):
        msg = format_task_received("proj_001", "director_script_review")
        self.assertIn("项目：proj_001", msg)
        self.assertIn("状态：已接收任务", msg)
        self.assertIn("节点：director_script_review", msg)

    def test_format_node_message_regular_node(self):
        state = {"project_name": "proj_001"}
        msg = format_node_message("writer", {"current_script": "abc"}, state)
        self.assertIn("项目：proj_001", msg)
        self.assertIn("状态：剧本初稿完成", msg)
        self.assertIn("节点：writer", msg)

    def test_format_node_message_gate_node(self):
        state = {
            "project_name": "proj_001",
            "current_script": "script",
            "director_script_review": "ok",
            "showrunner_script_review": "ok",
        }
        msg = format_node_message("user_gate_script", {"current_node": "user_gate_script"}, state)
        self.assertIn("项目：proj_001", msg)
        self.assertIn("状态：待你确认：剧本", msg)
        self.assertIn("请回复「通过」继续", msg)


if __name__ == "__main__":
    unittest.main()
