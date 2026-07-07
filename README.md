# 弱通信自适应虚拟电厂分布式协调控制系统

本项目包含 MATLAB 分布式协调控制算法、Python 通信质量感知与三态自适应切换后端，以及 Vue3 数字孪生监控前端。

## Python 后端运行

```powershell
.\.venv\Scripts\activate
cd python
python run_adaptive_demo.py --duration 120 --interval 1 --host 127.0.0.1 --port 8765
```

`run_adaptive_demo.py` 默认使用 `run_toxiproxy_adaptive_demo.py` 同一套 Toxiproxy 真实 TCP 探测路径产生 WebSocket 数据；如需退回纯公式仿真数据源，可追加 `--formula`。

前端联动演示时不要加 `--fast`，否则 120 秒演示会快速跑完。

## 通信信道模型

`python/vpp_adaptive/link_quality.py` 采用 Gilbert-Elliott 两状态马尔可夫信道模型生成链路质量。该模型把每条通信链路描述为 Good/Bad 两个状态：

- Good：低丢包、低时延，对应正常通信。
- Bad：高丢包、高时延，对应突发弱通信或局部中断。

Good/Bad 状态按马尔可夫转移概率切换，坏态停留时间自然形成突发聚集特征。这是网络化控制系统文献中刻画突发丢包的标准方法，常用于 H-infinity 控制、卡尔曼滤波补偿、电力系统阻尼控制等问题。

为了满足 120 秒演示的故障-恢复闭环，项目在固定两状态模型基础上加入缓慢变化的概率包络：周期中段提高 `p(Good->Bad)` 并降低 `p(Bad->Good)`，两端恢复为正常概率。不同链路使用不同脆弱度参数，因此会呈现“部分链路先中断、部分链路仍可用”的异构通信拓扑。

## Toxiproxy 真实网络损伤注入

项目支持 Shopify 开源的 Toxiproxy 作为真实 TCP 代理层。Gilbert-Elliott 模型仍负责决定每条链路在当前时刻的目标弱通信程度，但它不再直接作为前端展示数据源；系统会把模型输出写入 Toxiproxy 管理 API，动态调整每条链路代理的 `latency` toxic 和丢包等效 toxic。随后 5 个虚拟电厂节点通过真实 TCP socket 发送心跳探测，所有探测消息都经过对应 Toxiproxy 代理，状态机使用真实 ACK 往返耗时和真实超时比例计算通信质量。

Toxiproxy v2.12.0 的官方服务端不接受 `packet_loss` 作为原生 toxic 类型。代码会在启动时自动探测该能力；若不可用，则用概率性 `timeout` toxic 模拟真实丢包。由于每个探测心跳都新建一条 TCP 连接，`timeout` toxic 会让一部分真实探测连接超时，从而得到真实测量的丢包率，而不是读取内部模型变量。

首次运行前下载 Toxiproxy Windows 可执行文件：

```powershell
.\.venv\Scripts\activate
python tools\download_toxiproxy.py
```

单独启动 Toxiproxy 服务端：

```powershell
powershell -ExecutionPolicy Bypass -File tools\start_toxiproxy.ps1
```

一键运行真实网络损伤演示：

```powershell
.\.venv\Scripts\activate
python python\run_toxiproxy_adaptive_demo.py --duration 120 --interval 1
```

快速验证某条链路强制进入 Bad 状态：

```powershell
python python\run_toxiproxy_adaptive_demo.py --duration 20 --interval 1 --fast --force-bad-link 1-2 --force-bad-at 4 --force-bad-duration 6
```

查询 Toxiproxy 管理 API 中某条链路的代理和 toxic 配置：

```powershell
Invoke-RestMethod `
  -Headers @{ "User-Agent" = "adapvpp-toxiproxy-client/1.0" } `
  -Uri http://127.0.0.1:8474/proxies/vpp_1_2
```

## 最优性验证方法

本文的经济调度问题为严格凸二次规划问题。根据凸优化理论，KKT 条件是全局最优的充分必要条件。我们独立实现了基于 lambda 迭代法（二分搜索）的集中式基准解算器，验证分布式 ET-ADMM 算法收敛结果与该解析最优解的偏差在数值容差范围内，且各节点增量成本严格相等，满足 KKT 平稳性条件，从而在数学上证明所得调度方案的全局最优性，而非仅依赖算法自身的收敛判据。

运行以下脚本可生成集中式基准解与 ET-ADMM 分布式结果的对比表：

```matlab
run('matlab/analysis/optimality_verification.m')
```

结果导出到 `matlab/results/optimality_verification.csv`。
