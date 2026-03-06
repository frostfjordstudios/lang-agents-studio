"""影视动态提示词生成系统 - 主入口

使用方式：
    python main.py
"""

from src.agents.media_group.workflow import build_graph


def main():
    print("\n欢迎使用「影视动态提示词生成系统」\n")
    user_request = input("请输入您的创作需求：\n> ").strip()

    if not user_request:
        print("⚠️ 未输入需求，退出。")
        return

    print("🚀 工作流启动中...")
    app = build_graph()
    config = {"configurable": {"thread_id": "cli_session"}}
    initial_state = {"user_request": user_request, "reference_images": [], "reference_text": "", "project_name": "cli_project", "current_script": "", "director_script_review": "", "showrunner_script_review": "", "script_review_count": 0, "user_script_feedback": "", "director_breakdown": "", "art_design_content": "", "voice_design_content": "", "director_production_review": "", "production_review_count": 0, "user_production_feedback": "", "final_storyboard": "", "director_storyboard_review": "", "storyboard_review_count": 0, "scoring_director": "", "scoring_writer": "", "scoring_art": "", "scoring_voice": "", "scoring_storyboard": "", "scoring_showrunner": "", "final_scoring_report": "", "art_feedback_images": [], "art_feedback_result": "", "refined_storyboard": "", "current_node": ""}
    for event in app.stream(initial_state, config):
        for node_name, output in event.items():
            print(f"  ✅ {node_name} 完成")
    print("\n🎬 工作流结束！")


if __name__ == "__main__":
    main()
