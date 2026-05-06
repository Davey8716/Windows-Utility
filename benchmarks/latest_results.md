# Windows Utility Benchmark Snapshot

Interactive comparison uses a local-agent lower-bound model.
Agentic estimate = shell-equivalent median when available, otherwise app median, plus workflow tax.
Workflow tax uses 250 ms per orchestration step.

| Action | Category | App median ms | App p95 ms | Shell median ms | Agentic estimate ms | Speedup vs agentic | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Router Gateway Detection | Quick Action | 13.87 | 14.51 | 266.21 | 1516.21 | 109.3x | Runs the real ipconfig parse path and suppresses browser launch. |
| USB Drive Letter Detection | Inventory | 335.36 | 345.44 | 285.31 | 1785.31 | 5.3x | Benchmarks the PowerShell-backed USB drive discovery helper used by drive features. |
| Drive Inventory Scan | Inventory | 333.96 | 351.92 | 244.69 | 1744.69 | 5.2x | Measures the app-side drive scan with total/free space and ejectable detection. |
| Desktop Folder Creation | File Task | 0.31 | 0.34 | 230.18 | 2230.18 | 7088.9x | Uses a synthetic Desktop folder so the benchmark does not touch the real user profile. |
| Taskbar Shortcut Backup | File Task | 35.01 | 37.57 | 292.91 | 2292.91 | 65.5x | Copies 40 synthetic shortcut files and ignores non-shortcut files like the app does. |
| Brave Bookmarks Export | File Task | 59.98 | 65.95 | N/A | 2059.98 | 34.3x | Exports three synthetic Brave profiles with nested folders and hundreds of URLs. |
| Recycle Bin Age Cleanup | Maintenance | 32.37 | 35.18 | N/A | 1532.37 | 47.3x | Deletes old items from a synthetic recycle-bin fixture across two fake drives. |
| External Drive Poll Refresh | Resident Automation | 0.01 | 0.02 | N/A | N/A | N/A | Resident poll path that refreshes connected-drive state and notification deltas. |
