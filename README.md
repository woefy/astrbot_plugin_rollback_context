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

## 使用场景案例

下面是几个常见用法示例。为了方便理解，例子里的对话都是虚构的，重点是看：**现在想做什么 → 该用哪个命令 → 会看到什么输出 → 接下来怎么继续。**

### 案例 1：上一轮回答歪了，想删掉最后一个完整回合重来

**你现在想做什么？**  
Bot 刚刚把你的意思理解偏了，但更早的上文都还想保留，只想删掉最后一轮完整的一问一答。

**你要用哪个命令？**  
`/rlast`

**虚构对话示例**

```text
你：帮我写一个更正式一点的项目总结
Bot：好的，我给你写成轻松口语版吧……（明显偏题）
你：/rlast
Bot：已执行 rollback。
- type: 完整回合
- removed chain: user -> assistant
- user/head: 帮我写一个更正式一点的项目总结
- tail: 好的，我给你写成轻松口语版吧……
```

**后续怎么进行？**  
直接重新发你的要求，例如：

```text
你：重来，这次请写成正式汇报口吻，控制在 300 字内。
```

---

### 案例 2：工具链半路失败，想先预览再清掉脏尾巴

**你现在想做什么？**  
Bot 正在调工具，但半路失败或中断了。你怀疑当前上下文尾巴已经脏了，想先看它准备删什么，再决定是否执行。

**你要用哪个命令？**  
先用 `/clast`，确认后再用 `/clast y`

**虚构对话示例**

```text
你：帮我生成一张封面图
Bot：好，我来生成。
（工具调用中断 / 失败）
你：/clast
Bot：预览：将执行 /clast
- type: 未完成/中断的工具链尾巴
- removed chain: user -> assistant(tool_call) -> tool
- user/head: 帮我生成一张封面图
- tail: [tool result]
- 确认执行：/clast y
- 取消：/clast n
你：/clast y
Bot：已执行 clean。
- type: 未完成/中断的工具链尾巴
- removed chain: user -> assistant(tool_call) -> tool
- user/head: 帮我生成一张封面图
- tail: [tool result]
```

**后续怎么进行？**  
清掉尾巴后，再重新发一次请求，或者换一种说法继续：

```text
你：重新来一遍，这次先给我 3 个封面风格方向。
```

---

### 案例 3：命令用错了，插件会先拦你一下

**你现在想做什么？**  
你以为最后一轮是脏尾巴，结果它其实是一个完整回合；或者反过来，最后一轮明明是失败链，你却先用了 `/rlast`。

**你要用哪个命令？**  
先看插件提示，再切换到正确命令。

**虚构对话示例 A：完整回合误用 `/clast`**

```text
你：/clast
Bot：当前最后一轮是完整对话回合，建议使用 /rlast。/clast 更适合清理未完成、失败或中断的尾链。
```

**虚构对话示例 B：脏尾巴误用 `/rlast`**

```text
你：/rlast
Bot：当前最后一轮更像未完成/失败链，建议先用 /clast 预览待清理内容。
```

**后续怎么进行？**  
按照提示切到正确命令即可：

- 完整回合 → `/rlast`
- 脏尾巴 / 未完成回合 → `/clast` → `/clast y`

---

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
