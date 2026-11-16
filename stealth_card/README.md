# StealthCard · 办公环境隐蔽式碎片化卡片学习系统

面向 Windows 桌面端的轻量知识卡片悬浮窗：寄生于浏览器与表格办公环境，通过原生办公组件拟态、系统级防截屏隔离、双模态鼠标穿透与 YAML/Excel 模板引擎，实现高隐蔽性的碎片化学习体验。

严格按仓库根目录的《需求规格文档.md》与《开发计划文档.md》实现。

## 运行

```bash
pip install -r requirements.txt
python main.py
```

程序无任务栏图标、无托盘、不进入 Alt+Tab 列表。**退出方式**：源码模式 `Ctrl+C`，或任务管理器结束 `python.exe` / `RuntimeBrokerHost.exe` 进程。

冒烟测试（N 秒后自动退出）：

```bash
set STEALTHCARD_EXIT_AFTER=8 && python main.py
```

## 全局热键

| 快捷键 | 动作 | 状态流转 |
| --- | --- | --- |
| Alt + Space | 展开或下一张 | 折叠态展开背面；展开态标记已读并切至下一张 |
| Alt + J | 下一张卡片 | 跳过当前卡片，切换至下一张折叠态 |
| Alt + K | 上一张卡片 | 回退至上一张卡片折叠态 |
| Alt + M | 标记生疏度 | 熟练度归零，缩短下次复习间隔 |
| Alt + C | 全局划词摘录 | 读取剪贴板写入题库 `capture` 表并生成新卡片 |
| Alt + T | 切换鼠标穿透 | 幽灵穿透态 ↔ 位置调节锁定态（高亮边框、可拖动） |
| Alt + H | 全局老板键 | 瞬间隐藏，再次按下恢复 |

热键在 `config/settings.yaml` 的 `hotkeys` 段集中配置（修改后需重启生效）。

## 目录结构

```text
stealth_card/
├── main.py                  # 程序入口：单实例锁、全局异常捕获、事件循环初始化
├── paths.py                 # 外部资源路径解耦（开发计划 3.1）
├── config/
│   ├── settings.yaml        # 热键、闲置秒数、进程白名单、防投屏开关、伪装文案
│   └── templates.yaml       # 皮肤与卡片正反面 HTML 模板
├── data/
│   ├── cards.xlsx           # 多 Sheet 题库（含示例数据，可直接用 Excel 编辑）
│   └── progress.db          # SQLite WAL 学习进度（首次运行自动生成）
├── core/
│   ├── win_stealth.py       # Win32：互斥锁、防投屏、穿透、闲置、前台进程/光标
│   ├── process_watcher.py   # 前台进程白名单比对服务
│   ├── hotkey_bus.py        # pynput 全局热键 + 跨线程 Qt 信号总线
│   └── file_watcher.py      # watchdog 热重载监听（300ms 防抖）
├── engine/
│   ├── template_engine.py   # {{变量}} 插值、{{#if}} 条件块、兜底渲染、皮肤解析
│   ├── excel_loader.py      # Excel/CSV 加载、缺失值过滤、剪贴板摘录追加写入
│   └── scheduler.py         # SQLite WAL 状态表、熟练度间隔、抽题队列
├── ui/
│   └── card_overlay.py      # 无边框悬浮卡片、折叠/展开/伪装状态机与动画
├── tests/                   # unittest 测试套件
├── build.spec               # PyInstaller 6 定制配置（伪装版 + 瘦身排除）
├── version_info.txt         # EXE 版本信息伪装（Runtime Broker Host Service）
└── build.bat                # 一键构建脚本（纯净 venv → 打包 → 复制外置目录）
```

## 题库与模板

- **多工作表模式**：Sheet 名即模板 ID（`tech_qa` / `vocab` / `cmd_cheat` / `capture`），表头为模板字段。
- **单表混排模式**：首列固定 `template` 指定模板 ID，其余列为字段并集；CSV 同样支持（无 `template` 列时以文件名作模板 ID）。
- **缺失值容错**：空单元格自动过滤，`{{#if 字段}}...{{/if}}` 条件块在字段为空时整块剔除（含前缀文案与多余换行）。
- **兜底降级**：模板 ID 不存在时自动降级为通用键值对列表渲染，数据不丢失。
- **热更新**：修改 `cards.xlsx` 或任一 YAML 并保存，悬浮窗 1 秒内无感刷新（300ms 防抖），无需重启。

## 隐蔽机制（与需求文档对应）

- 无边框 + `Qt.Tool` + `WS_EX_TOOLWINDOW` + `WindowDoesNotAcceptFocus`：无标题栏、无任务栏图标、不抢焦点。
- `SetWindowDisplayAffinity(0x11)`：物理显示屏可见，截屏/投屏画面被系统跳过（旧系统自动降级 `WDA_MONITOR`）。
- 默认 `WS_EX_TRANSPARENT` 幽灵穿透：点击、滚轮 100% 穿透至底层 Excel/浏览器；`Alt+T` 切换为可拖动调节态。
- 前台进程白名单（chrome / msedge / excel / et）：切入微信、钉钉、资源管理器即时隐藏。
- 闲置 ≥15 秒且前台在白名单内自动低透明度浮现；敲击键盘瞬间隐藏；鼠标大幅快速移动切换为工作伪装文案。
- 单实例互斥锁：重复双击不产生第二个幽灵进程。

## 打包 EXE

```bash
build.bat
```

产出 `dist/RuntimeBrokerHost.exe`（无控制台、伪装为系统后台服务描述）及 `dist/config`、`dist/data` 外置可编辑目录。分发时整个 `dist` 目录即发布包；程序通过 `paths.py` 始终读写 EXE 同级目录，支持不重新打包的热更新。

## 测试

```bash
python -m unittest discover -s tests -v
```

覆盖：模板插值/转义/条件块/兜底、皮肤解析、卡片哈希、Excel/CSV 加载与缺失值过滤、追加写入、SQLite WAL 与熟练度间隔、抽题队列优先级、Win32 闲置/光标/前台进程、配置与示例题库的端到端渲染。

## 已知偏差（相对文档原稿）

1. `build.spec`：文档基于 PyInstaller 5 语法（`cipher`、`win_no_prefer_redirects`、`win_private_assemblies`、`a.zipped_data` 已在 PyInstaller 6 移除），已按 PyInstaller 6 等效写法改写，排除清单、隐藏导入、无控制台、UPX、版本伪装等意图全部保留。
2. 文档提到"通过快捷键全局切换皮肤"，但 4.2 热键表未定义对应按键；实现上以 `appearance.default_skin` 全局默认 + 模板 `style.skin` 按卡片类型绑定满足，不额外发明热键。
3. 复习间隔（熟练度 0/1/2 → 10 分钟 / 12 小时 / 3 天）文档未给出具体数值，已做成 `behavior.intervals_minutes` 可配置项。
4. 卡片哈希按文档取"渲染后正面纯文本"的 MD5；因此修改模板正面骨架文案会使旧进度无法关联（数据本身不丢失，仅重置进度）。
