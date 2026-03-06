import unittest

from src.tools.lark.msg.text_utils import build_mention_echo, clean_text_content


class TextUtilsTests(unittest.TestCase):
    def test_clean_text_content_strips_feishu_mentions(self):
        raw = '<at user_id="ou_xxx">管家</at>   你好 @_user_1'
        self.assertEqual(clean_text_content(raw), "你好")

    def test_clean_text_content_normalizes_whitespace(self):
        raw = "  hello \n\n world  "
        self.assertEqual(clean_text_content(raw), "hello world")

    def test_build_mention_echo_with_text(self):
        self.assertEqual(build_mention_echo("  测试消息 "), "收到你发送的消息：测试消息")

    def test_build_mention_echo_empty(self):
        self.assertEqual(build_mention_echo("   "), "收到你的@消息。")


if __name__ == "__main__":
    unittest.main()
