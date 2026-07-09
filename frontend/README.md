# 虚拟电厂数字孪生监控平台前端

Vue3 + Vite + TypeScript 前端大屏，用于展示弱通信自适应虚拟电厂的实时状态、通信质量、节点出力和 MATLAB 验证结果。

## 运行

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

访问 `http://127.0.0.1:5173`。

前端会优先连接 Python WebSocket `ws://127.0.0.1:8765`。如果后端未启动，会自动播放 `public/data/demo_telemetry.jsonl` 中的演示数据。
联动演示时建议后端使用 `python run_adaptive_demo.py --duration 120 --interval 1 --loop` 启动，避免单轮演示结束后 WebSocket 断开导致页面切换到离线 DEMO 模式。
