"""飞书云盘权限管理 + 部门文件夹体系

文件夹结构（在机器人云盘根目录下）：
  departments/
    management/
      housekeeper/
    media_group/
      showrunner/
      writer/
      director/
      art_design/
      voice_design/
      storyboard/
    dev_group/
      architect/

权限规则：
  管理层 = FEISHU_OWNER_OPEN_ID（你）+ management 部门机器人
  - 用户: full_access（所有文件夹，最高权限）
  - management 部门机器人: can_edit（可上传/查阅/下载，不可删除文件和文件夹）
  - 部门成员: can_edit（本部门文件夹，可添加/创建/修改，不可删除）
  - 员工个人: can_edit（自己的子文件夹，可添加/创建/修改，不可删除）
  - 不可跨部门查看（管理层除外）
"""

import os
import json
import logging
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

_owner_open_id = os.environ.get("FEISHU_OWNER_OPEN_ID", "").strip()

# 缓存: "dept_name" -> folder_token, "dept_name/agent_name" -> folder_token
_folder_cache: dict[str, str] = {}


# ── 底层 HTTP 工具 ──────────────────────────────────────────────────

def _get_access_token(app_id: str, app_secret: str) -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["tenant_access_token"]


def _api_call(access_token: str, method: str, url: str,
              body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={
                                     "Authorization": f"Bearer {access_token}",
                                     "Content-Type": "application/json; charset=utf-8",
                                 })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            return json.loads(body_text)
        except Exception:
            return {"code": e.code, "msg": body_text}


# ── 权限授予 ────────────────────────────────────────────────────────

def _grant_member(access_token: str, token: str, resource_type: str,
                  member_type: str, member_id: str, perm: str) -> bool:
    url = (f"https://open.feishu.cn/open-apis/drive/v1/permissions/{token}"
           f"/members?type={resource_type}&need_notification=false")
    result = _api_call(access_token, "POST", url, {
        "member_type": member_type,
        "member_id": member_id,
        "perm": perm,
    })
    code = result.get("code")
    if code == 0 or code == 1061012:  # 1061012 = 已有权限
        return True
    logger.debug("grant failed: %s -> %s perm=%s code=%s msg=%s",
                 token[:12], member_id[:12] if member_id else "?", perm,
                 code, result.get("msg"))
    return False


def grant_access(token: str, resource_type: str = "folder",
                 app_id: str = "", app_secret: str = "") -> bool:
    """给 FEISHU_OWNER_OPEN_ID 授予 full_access。"""
    if not _owner_open_id:
        return False
    app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
    app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        return False
    try:
        access_token = _get_access_token(app_id, app_secret)
        return _grant_member(access_token, token, resource_type,
                             "openid", _owner_open_id, "full_access")
    except Exception as e:
        logger.warning("grant_access 异常: %s", e)
        return False


# ── 文件夹管理 ──────────────────────────────────────────────────────

def _get_root_folder(access_token: str) -> str:
    url = "https://open.feishu.cn/open-apis/drive/explorer/v2/root_folder/meta"
    result = _api_call(access_token, "GET", url)
    if result.get("code") == 0:
        return result["data"]["token"]
    return ""


def _list_folder(access_token: str, folder_token: str) -> list[dict]:
    files = []
    page_token = ""
    while True:
        url = (f"https://open.feishu.cn/open-apis/drive/v1/files"
               f"?folder_token={folder_token}&page_size=50")
        if page_token:
            url += f"&page_token={page_token}"
        result = _api_call(access_token, "GET", url)
        if result.get("code") != 0:
            break
        for f in result.get("data", {}).get("files", []):
            files.append(f)
        if result.get("data", {}).get("has_more"):
            page_token = result["data"]["next_page_token"]
        else:
            break
    return files


def _find_subfolder(access_token: str, parent_token: str, name: str) -> str:
    for f in _list_folder(access_token, parent_token):
        if f.get("name") == name and f.get("type") == "folder":
            return f["token"]
    return ""


def _create_folder(access_token: str, parent_token: str, name: str) -> str:
    url = "https://open.feishu.cn/open-apis/drive/v1/files/create_folder"
    result = _api_call(access_token, "POST", url, {
        "name": name,
        "folder_token": parent_token,
    })
    if result.get("code") == 0:
        token = result.get("data", {}).get("token", "")
        logger.info("创建文件夹: %s -> %s", name, token)
        return token
    logger.warning("创建文件夹失败: %s code=%s msg=%s",
                   name, result.get("code"), result.get("msg"))
    return ""


def _ensure_folder(access_token: str, parent_token: str, name: str) -> str:
    existing = _find_subfolder(access_token, parent_token, name)
    if existing:
        return existing
    return _create_folder(access_token, parent_token, name)


# ── 部门文件夹体系 ──────────────────────────────────────────────────

def ensure_department_folders(app_id: str = "", app_secret: str = "") -> dict[str, str]:
    """创建部门 + 员工文件夹体系并设置权限。

    结构:
      departments/
        management/housekeeper/
        media_group/showrunner/ writer/ director/ ...
        dev_group/architect/

    权限:
      你 (FEISHU_OWNER_OPEN_ID): full_access 所有文件夹
      management 机器人: can_edit 所有部门文件夹（可上传/查阅/下载，不可删除）
      部门成员机器人: can_edit 本部门文件夹（可添加/创建/修改，不可删除）
      每个员工: can_edit 自己的子文件夹（可添加/创建/修改，不可删除）
      不可跨部门访问
    """
    global _folder_cache

    app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
    app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        logger.warning("缺少凭证，无法创建部门文件夹")
        return {}

    try:
        access_token = _get_access_token(app_id, app_secret)
    except Exception as e:
        logger.error("获取 token 失败: %s", e)
        return {}

    root = _get_root_folder(access_token)
    if not root:
        logger.warning("获取根目录失败（机器人可能缺少 drive:drive 权限），跳过文件夹初始化")
        return {}

    # 创建 departments 根
    dept_root = _ensure_folder(access_token, root, "departments")
    if not dept_root:
        logger.error("创建 departments 文件夹失败")
        return {}

    # 给你 full_access
    if _owner_open_id:
        _grant_member(access_token, dept_root, "folder",
                      "openid", _owner_open_id, "full_access")

    from src.agents.organization import GROUPS
    from src.tools.lark.msg.multi_bot import AGENT_BOTS

    # 收集 management 部门所有机器人 open_id（管理层）
    mgmt_bot_ids = []
    for agent_name in GROUPS.get("management", {}):
        bot = AGENT_BOTS.get(agent_name)
        if bot and bot.open_id:
            mgmt_bot_ids.append(bot.open_id)

    for dept_name, dept_members in GROUPS.items():
        # ── 创建部门文件夹 ──
        dept_token = _ensure_folder(access_token, dept_root, dept_name)
        if not dept_token:
            continue
        _folder_cache[dept_name] = dept_token

        # 你: full_access
        if _owner_open_id:
            _grant_member(access_token, dept_token, "folder",
                          "openid", _owner_open_id, "full_access")

        # 管理层机器人: can_edit 所有部门（可上传/查阅/下载，不可删除）
        for mgmt_oid in mgmt_bot_ids:
            _grant_member(access_token, dept_token, "folder",
                          "openid", mgmt_oid, "can_edit")

        # 本部门成员: can_edit 部门文件夹（可添加/创建/修改，不可删除）
        dept_bot_ids = []
        for agent_name in dept_members:
            bot = AGENT_BOTS.get(agent_name)
            if bot and bot.open_id:
                dept_bot_ids.append((agent_name, bot.open_id))
                _grant_member(access_token, dept_token, "folder",
                              "openid", bot.open_id, "can_edit")

        # ── 创建每个员工的子文件夹 ──
        for agent_name, bot_oid in dept_bot_ids:
            agent_token = _ensure_folder(access_token, dept_token, agent_name)
            if not agent_token:
                continue
            _folder_cache[f"{dept_name}/{agent_name}"] = agent_token

            # 你: full_access
            if _owner_open_id:
                _grant_member(access_token, agent_token, "folder",
                              "openid", _owner_open_id, "full_access")

            # 员工自己: can_edit（可添加/创建/修改，不可删除）
            _grant_member(access_token, agent_token, "folder",
                          "openid", bot_oid, "can_edit")

            # 管理层: can_edit（可上传/查阅/下载，不可删除）
            for mgmt_oid in mgmt_bot_ids:
                if mgmt_oid != bot_oid:  # 避免重复授权
                    _grant_member(access_token, agent_token, "folder",
                                  "openid", mgmt_oid, "can_edit")

    logger.info("=" * 50)
    logger.info("[部门文件夹体系]")
    for key, token in sorted(_folder_cache.items()):
        logger.info("  %s: %s", key, token)
    logger.info("=" * 50)

    return _folder_cache


# ── 查询接口 ────────────────────────────────────────────────────────

def get_department_folder(department: str) -> str:
    """获取部门文件夹 token。"""
    return _folder_cache.get(department, "")


def get_agent_folder(agent_name: str) -> str:
    """获取 Agent 个人文件夹 token。"""
    from src.agents.organization import get_agent
    agent = get_agent(agent_name)
    if not agent:
        return ""
    key = f"{agent.group}/{agent_name}"
    return _folder_cache.get(key, "")


def get_agent_department_folder(agent_name: str) -> str:
    """获取 Agent 所属部门的文件夹 token。"""
    from src.agents.organization import get_agent
    agent = get_agent(agent_name)
    if not agent:
        return ""
    return _folder_cache.get(agent.group, "")
