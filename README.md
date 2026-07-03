# 弱通信自适应虚拟电厂分布式协调控制系统

本项目包含 MATLAB 分布式协调控制算法、Python 通信质量感知与三态自适应切换后端，以及 Vue3 数字孪生监控前端。

## Python 后端运行

```powershell
.\.venv\Scripts\activate
cd python
python run_adaptive_demo.py --duration 120 --interval 1 --host 127.0.0.1 --port 8765
```

前端联动演示时不要加 `--fast`，否则 120 秒演示会快速跑完。

## 通信信道模型

`python/vpp_adaptive/link_quality.py` 采用 Gilbert-Elliott 两状态马尔可夫信道模型生成链路质量。该模型把每条通信链路描述为 Good/Bad 两个状态：

- Good：低丢包、低时延，对应正常通信。
- Bad：高丢包、高时延，对应突发弱通信或局部中断。

Good/Bad 状态按马尔可夫转移概率切换，坏态停留时间自然形成突发聚集特征。这是网络化控制系统文献中刻画突发丢包的标准方法，常用于 H-infinity 控制、卡尔曼滤波补偿、电力系统阻尼控制等问题。

为了满足 120 秒演示的故障-恢复闭环，项目在固定两状态模型基础上加入缓慢变化的概率包络：周期中段提高 `p(Good->Bad)` 并降低 `p(Bad->Good)`，两端恢复为正常概率。不同链路使用不同脆弱度参数，因此会呈现“部分链路先中断、部分链路仍可用”的异构通信拓扑。
