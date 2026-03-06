"""影视动态提示词生成系统 - 主入口

使用方式：
    python main.py
"""

from src.agents.media_group.workflow import build_graph
from src.workflow.state_factory import build_initial_state


def main():
    print("\n欢迎使用「影视动态提示词生成系统」\n")
    user_request = input("请输入您的创作需求：\n> ").strip()

    if not user_request:
        print("⚠️ 未输入需求，退出。")
        return

    print("🚀 工作流启动中...")
    app = build_graph()
    config = {"configurable": {"thread_id": "cli_session"}}
    initial_state = build_initial_state(user_request, project_name="cli_project")
    for event in app.stream(initial_state, config):
        for node_name, output in event.items():
            print(f"  ✅ {node_name} 完成")
    print("\n🎬 工作流结束！")


if __name__ == "__main__":
    main()
