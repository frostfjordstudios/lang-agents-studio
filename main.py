"""影视动态提示词生成系统 - 主入口

使用方式：
    python main.py
"""

from src.graph import run_interactive


def main():
    print("\n欢迎使用「影视动态提示词生成系统」\n")
    user_request = input("请输入您的创作需求：\n> ").strip()

    if not user_request:
        print("⚠️ 未输入需求，退出。")
        return

    run_interactive(user_request)


if __name__ == "__main__":
    main()
