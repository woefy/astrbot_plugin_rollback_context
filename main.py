from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@dataclass
class TailAction:
    mode: str
    start_idx: int
    end_idx: int
    removed: list[dict[str, Any]]
    summary: str
    keep_user: bool = False


@register(
    "astrbot_plugin_rollback_context",
    "woefy",
    "回滚最后一个完整回合，或预览并清理最后一个未完成/失败的本地上下文尾链。",
    "0.4.0",
)
class RollbackLastTurnPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context, config)
        self.context = context
        self.config: dict[str, Any] = dict(config or {})
        self.preview_max_chars = int(self.config.get("preview_max_chars", 80) or 80)
        self.strict_unknown_fallback = bool(self.config.get("strict_unknown_fallback", True))
        self._pending_clean: dict[str, dict[str, Any]] = {}

    @filter.command("rlast")
    async def rollback_last_turn(self, event: AstrMessageEvent) -> None:
        result = await self._handle_rollback(event)
        return event.plain_result(result)

    @filter.command("clast")
    async def clean_last_dirty_turn(self, event: AstrMessageEvent) -> None:
        result = await self._handle_clean(event)
        return event.plain_result(result)

    async def _handle_rollback(self, event: AstrMessageEvent) -> str:
        parsed = self._parse_command_text(event)
        conv_info = await self._get_conversation_bundle(event)
        if conv_info is None:
            return "当前会话还没有可处理的本地上下文。"

        umo, cid, conv, history = conv_info
        analysis = self._analyze_tail(history)

        if analysis["kind"] == "dirty_turn":
            return "当前最后一轮更像未完成/失败链，建议先用 /clast 预览待清理内容。"
        if analysis["kind"] == "unknown":
            if self.strict_unknown_fallback:
                return "当前最后一轮超出 rollback 的设计范围。请到 AstrBot WebUI 手动检查或管理这段会话。"
            return "当前最后一轮未命中 rollback 规则。为避免误删，本次未执行。"
        if analysis["kind"] != "completed_turn" or analysis["action"] is None:
            return "当前没有完整的一轮可回滚。"

        action: TailAction = analysis["action"]
        if parsed in {"dry", "preview"}:
            return self._format_preview(action, command_hint="/rlast", confirm_hint=None)

        new_history = history[: action.start_idx] + history[action.end_idx + 1 :]
        await self.context.conversation_manager.update_conversation(
            unified_msg_origin=umo,
            conversation_id=cid,
            history=new_history,
        )
        self._pending_clean.pop(self._pending_key(umo, cid), None)
        return self._format_apply_result(action, mode_name="rollback")

    async def _handle_clean(self, event: AstrMessageEvent) -> str:
        parsed = self._parse_command_text(event)
        conv_info = await self._get_conversation_bundle(event)
        if conv_info is None:
            return "当前会话还没有可处理的本地上下文。"

        umo, cid, conv, history = conv_info
        pending_key = self._pending_key(umo, cid)

        if parsed in {"y", "yes", "confirm"}:
            pending = self._pending_clean.get(pending_key)
            if not pending:
                return "当前没有待确认的 clean 预览。先发送 /clast 看看待删除内容。"
            if pending.get("history_signature") != self._history_signature(history):
                self._pending_clean.pop(pending_key, None)
                return "会话内容已经变化，之前的 clean 预览已失效。请重新发送 /clast。"

            action = TailAction(
                mode=pending["mode"],
                start_idx=pending["start_idx"],
                end_idx=pending["end_idx"],
                removed=pending["removed"],
                summary=pending["summary"],
                keep_user=bool(pending.get("keep_user", False)),
            )
            new_history = history[: action.start_idx] + history[action.end_idx + 1 :]
            await self.context.conversation_manager.update_conversation(
                unified_msg_origin=umo,
                conversation_id=cid,
                history=new_history,
            )
            self._pending_clean.pop(pending_key, None)
            return self._format_apply_result(action, mode_name="clean")

        if parsed in {"n", "no", "cancel"}:
            existed = self._pending_clean.pop(pending_key, None)
            return "已取消本次 clean 预览。" if existed else "当前没有待取消的 clean 预览。"

        analysis = self._analyze_tail(history)
        if analysis["kind"] == "completed_turn":
            return "当前最后一轮是完整对话回合，建议使用 /rlast。/clast 更适合清理未完成、失败或中断的尾链。"
        if analysis["kind"] == "unknown":
            if self.strict_unknown_fallback:
                return "当前最后一轮超出 clean 的设计范围。请到 AstrBot WebUI 手动检查或管理这段会话。"
            return "当前最后一轮未命中 clean 规则。为避免误删，本次未执行。"
        if analysis["kind"] != "dirty_turn" or analysis["action"] is None:
            return "当前没有可 clean 的脏尾巴。"

        action = analysis["action"]
        self._pending_clean[pending_key] = {
            "mode": action.mode,
            "start_idx": action.start_idx,
            "end_idx": action.end_idx,
            "removed": action.removed,
            "summary": action.summary,
            "keep_user": action.keep_user,
            "history_signature": self._history_signature(history),
        }
        return self._format_preview(action, command_hint="/clast", confirm_hint="/clast y")

    async def _get_conversation_bundle(
        self, event: AstrMessageEvent
    ) -> tuple[Any, str, Any, list[dict[str, Any]]] | None:
        conv_mgr = self.context.conversation_manager
        umo = event.unified_msg_origin
        cid = await conv_mgr.get_curr_conversation_id(umo)
        if not cid:
            return None

        conv = await conv_mgr.get_conversation(umo, cid)
        if not conv:
            return None

        raw_history = getattr(conv, "history", None)
        if raw_history is None and hasattr(conv, "content"):
            raw_history = getattr(conv, "content")
        history = self._load_history(raw_history)
        if not history:
            return None
        return umo, cid, conv, history

    def _analyze_tail(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        if not history:
            return {"kind": "empty", "action": None}

        last_user_idx = self._find_last_user_index(history)
        if last_user_idx is None:
            return {"kind": "unknown", "action": None}

        suffix = history[last_user_idx:]
        if not suffix or not isinstance(suffix[0], dict) or suffix[0].get("role") != "user":
            return {"kind": "unknown", "action": None}
        if any(not isinstance(msg, dict) for msg in suffix):
            return {"kind": "unknown", "action": None}
        if any(msg.get("role") not in {"user", "assistant", "tool"} for msg in suffix):
            return {"kind": "unknown", "action": None}

        if self._looks_like_completed_chain(suffix):
            return {
                "kind": "completed_turn",
                "action": TailAction(
                    mode="rollback",
                    start_idx=last_user_idx,
                    end_idx=len(history) - 1,
                    removed=suffix,
                    summary="完整回合",
                ),
            }

        if self._looks_like_dirty_chain(suffix):
            summary = (
                "末尾停在用户消息，尚未进入有效回复链"
                if len(suffix) == 1
                else "未完成/中断的工具链尾巴"
            )
            return {
                "kind": "dirty_turn",
                "action": TailAction(
                    mode="clean",
                    start_idx=last_user_idx,
                    end_idx=len(history) - 1,
                    removed=suffix,
                    summary=summary,
                ),
            }

        return {"kind": "unknown", "action": None}

    def _find_last_user_index(self, history: list[dict[str, Any]]) -> int | None:
        for i in range(len(history) - 1, -1, -1):
            msg = history[i]
            if isinstance(msg, dict) and msg.get("role") == "user":
                return i
        return None

    def _looks_like_completed_chain(self, removed: list[dict[str, Any]]) -> bool:
        if len(removed) < 2:
            return False
        if removed[0].get("role") != "user":
            return False
        if removed[-1].get("role") != "assistant":
            return False
        if self._is_tool_call_assistant(removed[-1]):
            return False

        for msg in removed[1:-1]:
            role = msg.get("role")
            if role == "tool":
                continue
            if role == "assistant" and self._is_tool_call_assistant(msg):
                continue
            return False
        return True

    def _looks_like_dirty_chain(self, removed: list[dict[str, Any]]) -> bool:
        if not removed or removed[0].get("role") != "user":
            return False
        if len(removed) == 1:
            return True

        seen_tool_or_toolcall = False
        for msg in removed[1:]:
            role = msg.get("role")
            if role == "tool":
                seen_tool_or_toolcall = True
                continue
            if role == "assistant" and self._is_tool_call_assistant(msg):
                seen_tool_or_toolcall = True
                continue
            return False
        return seen_tool_or_toolcall

    def _is_tool_call_assistant(self, msg: dict[str, Any]) -> bool:
        if msg.get("role") != "assistant":
            return False
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            return True
        content = msg.get("content")
        if isinstance(content, list):
            has_text = any(
                isinstance(item, dict) and item.get("type") == "text" and str(item.get("text", "")).strip()
                for item in content
            )
            has_think = any(
                isinstance(item, dict) and item.get("type") == "think"
                for item in content
            )
            if has_think and not has_text:
                return True
        return False

    def _load_history(self, raw_history: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if raw_history is None:
            return []
        if isinstance(raw_history, list):
            return list(raw_history)
        try:
            parsed = json.loads(raw_history)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    def _parse_command_text(self, event: AstrMessageEvent) -> str:
        raw = ""
        for attr in ("message_str", "raw_message", "text"):
            value = getattr(event, attr, None)
            if isinstance(value, str) and value.strip():
                raw = value.strip()
                break
        if not raw:
            try:
                raw = str(event.get_message_str()).strip()  # type: ignore[attr-defined]
            except Exception:
                raw = ""
        parts = raw.split()
        if len(parts) <= 1:
            return ""
        return parts[1].strip().lower()

    def _history_signature(self, history: list[dict[str, Any]]) -> str:
        tail = history[-8:]
        try:
            return json.dumps(tail, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(tail)

    def _pending_key(self, umo: Any, cid: str) -> str:
        return f"{umo}::{cid}"

    def _format_preview(self, action: TailAction, command_hint: str, confirm_hint: str | None) -> str:
        removed_roles = " -> ".join(self._role_label(msg) for msg in action.removed)
        user_preview = self._preview_text(action.removed[0])
        tail_preview = self._preview_text(action.removed[-1])
        lines = [
            f"预览：将执行 {command_hint}",
            f"- type: {action.summary}",
            f"- removed chain: {removed_roles}",
            f"- user/head: {user_preview}",
            f"- tail: {tail_preview}",
        ]
        if confirm_hint:
            lines.append(f"- 确认执行：{confirm_hint}")
            lines.append("- 取消：/clast n")
        return "\n".join(lines)

    def _format_apply_result(self, action: TailAction, mode_name: str) -> str:
        removed_roles = " -> ".join(self._role_label(msg) for msg in action.removed)
        user_preview = self._preview_text(action.removed[0])
        tail_preview = self._preview_text(action.removed[-1])
        return (
            f"已执行 {mode_name}。\n"
            f"- type: {action.summary}\n"
            f"- removed chain: {removed_roles}\n"
            f"- user/head: {user_preview}\n"
            f"- tail: {tail_preview}"
        )

    def _role_label(self, msg: dict[str, Any]) -> str:
        role = msg.get("role", "?")
        if role == "assistant" and self._is_tool_call_assistant(msg):
            return "assistant(tool_call)"
        return str(role)

    def _preview_text(self, msg: dict[str, Any]) -> str:
        content = msg.get("content")
        if isinstance(content, str):
            text = content.strip().replace("\n", " ")
            max_chars = max(20, int(getattr(self, "preview_max_chars", 80) or 80))
            return text[:max_chars] + ("…" if len(text) > max_chars else "") if text else "[empty]"
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    t = str(item.get("text", "")).strip()
                    if t:
                        parts.append(t)
            text = " ".join(parts).replace("\n", " ").strip()
            if text:
                max_chars = max(20, int(getattr(self, "preview_max_chars", 80) or 80))
                return text[:max_chars] + ("…" if len(text) > max_chars else "")
        if msg.get("tool_calls"):
            return "[tool calls]"
        if msg.get("tool_call_id"):
            return "[tool result]"
        return "[empty]"
