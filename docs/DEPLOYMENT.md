# Klipper TRSYNC Adaptive Timeout 部署指南

## 概述

此补丁为 Klipper 添加了自适应 TRSYNC timeout 功能，用于解决 multi-MCU + CAN toolhead 环境下的 "Communication timeout during homing" 错误。

## 问题背景

在 multi-MCU + CAN 架构中，Z homing 过程经常出现超时错误，原因是：
- 当前 TRSYNC_TIMEOUT 硬编码为 25ms
- 实际延迟包括：Host scheduling jitter + USB latency + CAN latency + MCU processing time
- 这些延迟累加后经常超过 25ms，导致误判超时

## 解决方案

实现自适应 timeout 机制：
- 基于实时 RTT（Round-Trip Time）动态计算 timeout
- 使用 EWMA（指数加权移动平均）平滑 RTT 波动
- 加入安全上下限保护
- 完全在 Host 端（klippy）实现，无需修改 MCU 固件

## 部署步骤

### 1. 应用补丁

```bash
cd /path/to/klipper
git apply /path/to/klipper_trsync_adaptive.patch
```

或者手动复制文件：
```bash
# 复制新模块
cp klipper_origin/klipper/klippy/extras/trsync_adaptive.py \
   /path/to/klipper/klippy/extras/

# 替换 mcu.py（建议先备份）
cp /path/to/klipper/klippy/mcu.py /path/to/klipper/klippy/mcu.py.backup
cp klipper_origin/klipper/klippy/mcu.py \
   /path/to/klipper/klippy/
```

### 2. 修改配置文件

编辑 `printer.cfg`，在 `[printer]` 段添加：

```ini
[printer]
trsync_timeout_mode: adaptive
trsync_min_timeout: 0.025
trsync_max_timeout: 0.120
trsync_margin: 0.008
trsync_sigma_multiplier: 4.0
trsync_ewma_alpha: 0.2
```

详细配置说明请参考 `docs/printer.cfg.example`。

### 3. 重启 Klipper

```bash
sudo systemctl restart klipper
```

**注意：无需重新编译或刷写 MCU 固件！**

### 4. 验证部署

查看日志确认 adaptive timeout 已启用：

```bash
tail -f /tmp/klippy.log | grep -i trsync
```

你应该看到类似的日志：
```
TRSyncAdaptive initialized for MCU 'mcu': min=0.025 max=0.120 ...
TriggerDispatch: Adaptive timeout mode enabled
```

### 5. 测试 Homing

执行 Z homing 测试：
```gcode
G28 Z
```

检查日志中的 timeout 计算：
```
TriggerDispatch.start: Using adaptive timeout=0.045123 s for 2 MCU(s)
TRSyncAdaptive timeout for MCU 'mcu': rtt_avg=0.012000 std=0.003000 timeout=0.045123
```

## 配置调优

### 典型 RTT 和 Timeout 对应关系

| RTT  | Calculated Timeout | 适用场景 |
|------|-------------------|---------|
| 5ms  | ~25ms            | Single MCU / USB |
| 8ms  | ~35ms            | Multi-MCU USB |
| 12ms | ~50ms            | Multi-MCU + CAN (轻度负载) |
| 20ms | ~80ms            | Multi-MCU + CAN (高负载) |

### 如果仍然出现 Timeout

1. **检查日志中的 RTT 值**
   ```bash
   grep "rtt_avg" /tmp/klippy.log
   ```

2. **如果 timeout 达到 max_timeout**
   - 增加 `trsync_max_timeout`（例如 0.150 或 0.200）

3. **如果 RTT 波动很大**
   - 降低 `trsync_ewma_alpha`（例如 0.1）
   - 增加 `trsync_sigma_multiplier`（例如 5.0）

4. **如果偶发 timeout**
   - 增加 `trsync_margin`（例如 0.010 或 0.012）

### 回退到固定模式

如果需要恢复原始行为，只需修改配置：

```ini
[printer]
trsync_timeout_mode: fixed
```

然后重启 Klipper。

## 文件清单

- `klippy/extras/trsync_adaptive.py` - 新增模块
- `klippy/mcu.py` - 修改文件（添加 adaptive timeout 支持）
- `docs/printer.cfg.example` - 配置示例
- `docs/DEPLOYMENT.md` - 本文档

## 技术细节

### EWMA 算法

```python
# 更新平均值
diff = rtt - rtt_avg
rtt_avg += alpha * diff

# 更新方差
rtt_var += alpha * (diff*diff - rtt_var)

# 计算标准差
std = sqrt(max(rtt_var, 0))
```

### Timeout 计算

```python
timeout = clamp(
    rtt_avg + sigma_multiplier * std + margin,
    min_timeout,
    max_timeout
)
```

### 安全设计

1. **默认关闭**：`trsync_timeout_mode` 默认为 "fixed"
2. **Fallback 机制**：RTT 不可用时返回 `min_timeout`
3. **上限保护**：`max_timeout` 防止故障时长时间运动
4. **下限保护**：`min_timeout` 确保不低于安全值

## 故障排查

### 问题：Klipper 启动失败

**可能原因：**
- 配置文件语法错误
- 模块导入失败

**解决方法：**
```bash
# 查看完整错误日志
cat /tmp/klippy.log

# 检查配置文件语法
grep -A 10 "\[printer\]" printer.cfg

# 确认模块文件存在
ls -l /path/to/klipper/klippy/extras/trsync_adaptive.py
```

### 问题：仍然出现 Timeout 错误

**可能原因：**
- `max_timeout` 设置过小
- RTT 波动过大
- 系统负载过高

**解决方法：**
1. 增加 `max_timeout` 到 0.200
2. 降低 `trsync_ewma_alpha` 到 0.1
3. 增加 `trsync_sigma_multiplier` 到 5.0
4. 检查系统 CPU 负载

### 问题：Adaptive 模式未生效

**检查步骤：**
```bash
# 1. 确认配置已加载
grep "trsync_timeout_mode" printer.cfg

# 2. 查看日志确认模式
grep "Adaptive timeout mode" /tmp/klippy.log

# 3. 确认模块已导入
grep "TRSyncAdaptive" /tmp/klippy.log
```

## 性能影响

- **CPU 开销**：极小（每次 homing 仅计算一次）
- **内存开销**：每个 MCU 约 100 字节
- **延迟影响**：无（不改变通信协议）

## 兼容性

- **Klipper 版本**：v0.11.0 及以上
- **MCU 固件**：无需修改，完全兼容
- **现有配置**：默认关闭，不影响现有机器

## 许可证

本补丁遵循 Klipper 的 GNU GPLv3 许可证。

## 支持

如有问题，请提供以下信息：
1. Klipper 版本
2. MCU 配置（数量、连接方式）
3. `/tmp/klippy.log` 中的相关日志
4. `printer.cfg` 中的 `[printer]` 段配置
