# 剪道（Rollback Context）

一个给 AstrBot 用的本地上下文修剪插件。

它不会撤回飞书、Telegram、Discord 等平台上的表面消息，也不会修改长期记忆、知识库或外部文件；它只处理 **AstrBot 当前会话的本地 conversation history**，用于修剪最近一轮对后续生成造成污染的上下文。

## 风险提示

这是一个**功能简单但风险较高**的插件。

原因不在于它会动很多地方，而恰恰在于：它会**直接修改 AstrBot 当前会话的本地 conversation history**。一旦执行成功，被删掉的那一段本地上下文通常不会自动恢复。

使用前请明确以下边界：

- 它修改的是 **AstrBot 本地会话记录**，不是消息平台上的表面消息
- 它不会帮你撤回飞书 / Telegram / Discord 上已经发出去的消息
- 它也不会联动修改长期记忆、知识库或外部文件
- 如果误删，只能依赖你自己的数据库备份、导出记录或手动恢复

如果你不确定最后一轮该不该删，建议先用预览命令，不要直接执行。

## 功能概览

插件提供两个命令：

- `/rlast`：回滚最后一个**完整回合**
- `/clast`：预览并清理最后一个**脏尾巴 / 未完成回合**

当前版本优先推荐在**私聊 / 单人会话**中使用。

## 适用场景

- 最近一轮输出歪了，想删掉最后一轮重新来，但不想重开整段会话
- tool call / skill 调试时留下了半截失败链，污染了后续上下文
- 想保留更早的对话，只修剪最后一轮完整回合或最后一段脏尾巴

## 命令说明

命令名故意收得很短：

- `/rlast` 里的 `r` 来自 **rollback**，`last` 表示只处理**最后一个完整回合**
- `/clast` 里的 `c` 可以理解成 **clean**，也可以理解成 **cut**，对应清理或剪掉**最后一个脏尾巴 / 未完成回合**

这样命名的目的，是让命令既短、好记，又尽量避免和更通用的 `/rollback`、`/clean` 一类命令撞名。

### `/rlast`

用于处理 **最后一个完整回合**。

默认直接执行，也支持只预览不落盘：

- `/rlast`
- `/rlast dry`
- `/rlast preview`

适用形态包括：

- `user -> assistant`
- `user -> assistant(tool_call) -> tool -> assistant`
- `user -> assistant(tool_call) -> tool -> assistant(tool_call) -> tool -> assistant`

如果最后一轮更像未完成或失败链，插件不会硬删，而是提醒你改用 `/clast`。

### `/clast`

用于处理 **最后一个脏回合 / 未完成尾链 / 中断尾巴**。

默认只做预览，确认后才执行：

- `/clast` → 预览
- `/clast y` → 确认执行
- `/clast n` → 取消

适用形态包括：

- `user`
- `user -> assistant(tool_call)`
- `user -> assistant(tool_call) -> tool`
- `user -> assistant(tool_call) -> tool -> assistant(tool_call) -> tool`

`/clast` 当前允许把最后那个 `user` 一起清掉，因为消息平台上的原始消息并不会消失，清理的只是 AstrBot 本地会话上下文。

## 安全策略

这个插件不会“尽量猜”，而是**优先安全**：

- 在脏尾巴上误用 `/rlast` → 提示改用 `/clast`
- 在完整回合上误用 `/clast` → 提示改用 `/rlast`
- 如果最后一轮结构超出当前设计范围 → **拒绝自动处理**，并提示去 AstrBot WebUI 手动管理

当前插件只分析：
**最后一个 `user` 之后的整段尾链**

并将其分为：

- `completed_turn`
- `dirty_turn`
- `unknown`

其中：

- `completed_turn` → 交给 `/rlast`
- `dirty_turn` → 交给 `/clast`
- `unknown` → 不自动删除，转 WebUI 手动处理

## 安装

将插件目录放入 AstrBot 的 `data/plugins/`，或通过 AstrBot WebUI 上传 zip 安装。

插件目录应包含：

- `main.py`
- `metadata.yaml`
- `README.md`
- `_conf_schema.json`

## 配置项

### `preview_max_chars`
预览文本的最大长度。过长时会自动截断。

### `strict_unknown_fallback`
当最后一轮尾链不属于 `completed_turn` / `dirty_turn` 时，是否强制拒绝自动处理并提示去 WebUI 手动管理。建议保持开启。

## 作者与协助

- Author: `woefy`
- Assisted by: 团子（AI assistant）
