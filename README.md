# StealthCard · 办公环境隐蔽式碎片化卡片学习系统

一款运行于 Windows 桌面的轻量知识卡片软件：寄生于浏览器与表格办公环境，通过原生办公组件拟态、系统级防截屏隔离、双模态鼠标穿透与 YAML/Excel 自定义模板引擎，实现高隐蔽性的碎片化学习体验。

## 仓库内容

| 路径 | 说明 |
| --- | --- |
| `stealth_card/` | 完整应用工程（PyQt5 + openpyxl + SQLite WAL + pynput + watchdog） |
| `需求规格文档.md` | 产品定位、视觉伪装、模板引擎、交互与安全机制的完整需求 |
| `开发计划文档.md` | 技术选型、五阶段里程碑、EXE 打包与进程伪装方案 |

应用自身的详细说明（热键表、配置项、打包步骤、验收清单、已知偏差）见 [`stealth_card/README.md`](stealth_card/README.md)。

## 快速开始

```bash
cd stealth_card
pip install -r requirements.txt
python main.py
```

运行后无任务栏图标、不进入 Alt+Tab；通过全局热键操作（Alt+Space 展开、Alt+J/K 翻页、Alt+H 老板键），退出请用任务管理器结束进程。

打包发布：

```bash
cd stealth_card
build.bat
```

产出 `dist/RuntimeBrokerHost.exe` 与可热更新的 `dist/config`、`dist/data` 外置目录。

## 测试

```bash
cd stealth_card
python -m unittest discover -s tests -v
```
