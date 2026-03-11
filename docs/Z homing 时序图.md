下面是根据 **Klipper 源码执行路径（klippy + MCU firmware）**整理出的 **Z Homing（multi-MCU + CAN）完整时序图**。
我会先给出 **完整时序图**，然后解释 **每个阶段源码在什么地方执行**，这样你可以直接对应源码调试。

为了清晰，参与者定义：

```text
Host      = klippy (Python)
MCU_A     = 主板 MCU (控制 Z stepper)
MCU_B     = toolhead MCU (probe)
CAN       = CAN bus
```

---

# 一、Z Homing 完整时序图

```text
        Host (klippy)            MCU_A (Z stepper)            MCU_B (Probe)
             |                           |                           |
             | G28 Z command             |                           |
             |-------------------------->|                           |
             |                           |                           |
             | create TriggerDispatch    |                           |
             | create MCU_trsync         |                           |
             |                           |                           |
             | trsync_start              |                           |
             |-------------------------->|                           |
             |                           |                           |
             |                           | CAN broadcast trsync_start|
             |                           |-------------------------->|
             |                           |                           |
             |                           | prepare trigger           |
             |                           | prepare trigger           |
             |                           |                           |
             | schedule Z stepper move   |                           |
             |-------------------------->|                           |
             |                           | start stepping            |
             |                           |                           |
             | periodic trsync_query     |                           |
             |-------------------------->|                           |
             |                           | CAN forward query         |
             |                           |-------------------------->|
             |                           |                           |
             |                           |<---- trsync_state --------|
             |<------ trsync_state ------|                           |
             |                           |                           |
             | update last_response      |                           |
             |                           |                           |
             | periodic check timeout    |                           |
             |                           |                           |
             |                           |                           |
             |                 probe triggered (MCU_B)               |
             |                           |<---------------------------|
             |                           |                           |
             |                           | CAN trigger notify        |
             |                           |-------------------------->|
             |                           |                           |
             |<----- trigger event ------|                           |
             |                           |                           |
             | stop stepper              |                           |
             |-------------------------->|                           |
             |                           | stop motion               |
             |                           |                           |
             | homing finished           |                           |
```

---

# 二、关键阶段解释

整个过程其实分 **5个阶段**：

```text
1 初始化 TRSYNC
2 启动 stepper motion
3 TRSYNC 心跳同步
4 probe 触发
5 stepper 停止
```

---

# 三、阶段1：初始化 TRSYNC

触发：

```gcode
G28 Z
```

进入：

```text
klippy/homing.py
```

函数：

```python
home_rails()
```

然后创建：

```text
TriggerDispatch
```

源码：

```python
klippy/mcu.py
class TriggerDispatch
```

它会为每个 MCU 创建：

```text
MCU_trsync
```

对象。

目的：

```text
同步 trigger 状态
```

---

# 四、阶段2：启动 TRSYNC

Host 发送：

```text
trsync_start
```

消息。

流程：

```text
Host → MCU_A
MCU_A → CAN → MCU_B
```

作用：

```text
所有 MCU 进入 trigger monitoring
```

源码：

```python
MCU_trsync.start()
```

发送：

```text
trsync_start
```

MCU firmware 中：

```text
src/trsync.c
```

初始化：

```text
trigger monitor
```

---

# 五、阶段3：Z stepper 开始运动

Host 发送 step queue：

```text
queue_step
```

路径：

```text
Host → MCU_A
```

Z stepper 开始：

```text
向下运动
```

同时：

```text
probe monitoring active
```

---

# 六、阶段4：TRSYNC 心跳

这是 **timeout 检测的关键阶段**。

Host 定期发送：

```text
trsync_query
```

周期：

```text
~10ms
```

流程：

```text
Host
 ↓
MCU_A
 ↓
CAN
 ↓
MCU_B
```

MCU_B 返回：

```text
trsync_state
```

返回路径：

```text
MCU_B → CAN → MCU_A → Host
```

Host 更新：

```python
last_response
```

如果：

```text
now - last_response > 0.025
```

就触发：

```text
Communication timeout during homing
```

---

# 七、阶段5：Probe 触发

当 nozzle 碰到 bed：

```text
probe trigger
```

发生在：

```text
MCU_B
```

MCU_B firmware：

```text
endstop interrupt
```

然后：

```text
trigger event
```

通过 CAN 通知：

```text
MCU_A
```

MCU_A 立即：

```text
stop stepper
```

同时 Host 收到：

```text
trigger event
```

Homing 完成。

---

# 八、TRSYNC timeout 发生在哪里

timeout 检测在 Host：

源码：

```text
klippy/mcu.py
```

逻辑：

```python
if eventtime > last_response + TRSYNC_TIMEOUT:
    raise error
```

默认：

```text
TRSYNC_TIMEOUT = 0.025
```

也就是：

```text
25ms
```

---

# 九、CAN 环境的额外延迟

multi-MCU + CAN 时：

一次 query 路径：

```text
Host
 ↓
USB
 ↓
MCU_A
 ↓
CAN
 ↓
MCU_B
 ↓
CAN
 ↓
MCU_A
 ↓
USB
 ↓
Host
```

总延迟：

```text
Host scheduling
+ USB latency
+ CAN latency
+ MCU processing
```

通常：

```text
5-20ms
```

极端：

```text
30-40ms
```

于是：

```text
>25ms timeout
```

---

# 十、为什么 Z homing 比 XY 更容易 timeout

XY homing：

```text
endstop 和 stepper 在同一 MCU
```

路径：

```text
MCU local interrupt
```

没有：

```text
TRSYNC
CAN
```

所以几乎不会 timeout。

---

# 十一、完整执行路径（源码）

Z homing multi-MCU 调用链：

```text
G28
 ↓
homing.py
 ↓
TriggerDispatch
 ↓
MCU_trsync.start()
 ↓
trsync_start
 ↓
queue_step
 ↓
trsync_query loop
 ↓
probe trigger
 ↓
stop_stepper
```

核心文件：

```text
klippy/homing.py
klippy/mcu.py
src/trsync.c
```

---

# 十二、为什么 RTT adaptive 能解决问题

原始逻辑：

```text
timeout = 25ms
```

如果：

```text
Linux jitter 30ms
```

就会：

```text
false timeout
```

RTT adaptive：

```text
timeout = RTT + jitter margin
```

例如：

```text
RTT = 8ms
std = 6ms
timeout ≈ 38ms
```

避免误判。

---

# 十三、产品调试建议

如果你要 **确认瓶颈在哪**，建议抓：

```text
klippy.log
```

关注：

```text
MCU round-trip time
Reactor latency
trsync timeout
```

如果：

```text
RTT <10ms
timeout
```

通常就是：

```text
host scheduling jitter
```

---

如果你愿意，我可以再给你一个 **更关键的东西**：

我可以画出 **Klipper multi-MCU homing 的内部线程模型图**（Host reactor + MCU interrupt + CAN ISR），
这个图能解释 **为什么某些机器即使 RTT 很低仍然会 timeout**。
