# 升级版 Miner.py 功能说明

## 核心升级点
1.  **🚀 极速多线程 (Multi-threading)**:
    -   使用 `ThreadPoolExecutor` 并发执行，效率大幅提升。
    -   默认开启 5 个线程 (`MAX_WORKERS=5`)。

2.  **📊 可视化进度条**:
    -   集成 `tqdm` 库，实时显示挖掘进度。
    -   动态展示：当前挖掘的种子词、已发现的唯一关键词总数。

3.  **🌍 双引擎数据源 (Dual Source)**:
    -   **Google**: 经典建议接口。
    -   **Bing**: 新增 Bing 建议接口，有效补充长尾词。

4.  **⛏️ 深度挖掘 (Deep Mining)**:
    -   **A-Z 后缀遍历**: 自动对每个种子词进行 `a-z` 和 `0-9` 的全量后缀扫描。
    -   覆盖面扩大约 36 倍。

5.  **🛡️ 防封策略**:
    -   **随机 User-Agent**: 模拟不同浏览器。
    -   **随机延迟**: 每次请求随机等待 0.5 - 1.5 秒。

## 使用方法
1.  确保已安装依赖：
    ```bash
    pip install tqdm requests
    ```
2.  运行脚本：
    ```bash
    python3 MasterTool/miner.py
    ```

脚本会自动读取 `MasterTool/seeds.txt` 并将结果保存至 `MasterTool/raw_keywords.csv`。