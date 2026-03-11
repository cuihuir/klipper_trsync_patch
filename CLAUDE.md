# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 Klipper 3D 打印机固件的补丁项目，为 TRSYNC（同步触发）模块添加自适应超时功能。主要解决 multi-MCU + CAN toolhead 环境下的 "Communication timeout during homing" 错误。

**核心技术**：
- 使用 EWMA（指数加权移动平均）算法动态计算超时时间
- 基于实时 RTT（往返时间）测量自适应调整
- 纯 Host 端实现，无需修改 MCU 固件

## 常用命令

### 测试
```bash
# 运行单元测试
python3 test_trsync_adaptive.py

# 测试应该输出所有测试通过的消息
```

### 安装/卸载
```bash
# 安装补丁到默认 Klipper 路径 (~/klipper)
./install.sh

# 安装到自定义路径
./install.sh --klipper-path /path/to/klipper

# 卸载补丁
./uninstall.sh

# 卸载自定义路径
./uninstall.sh --klipper-path /path/to/klipper
```

### 应用 Git Patch
```bash
# 进入 Klipper 目录
cd ~/klipper

# 检查 patch 是否可以应用
git apply --check ~/klipper_trsync_patch/klipper_trsync_adaptive.patch

# 应用 patch
git apply ~/klipper_trsync_patch/klipper_trsync_adaptive.patch

# 如果需要回退
git apply -R ~/klipper_trsync_patch/klipper_trsync_adaptive.patch
```

### 验证安装
```bash
# 查看 Klipper 日志中的 TRSYNC 相关信息
tail -f /tmp/klippy.log | grep -i trsync

# 检查 Klipper 服务状态
systemctl status klipper

# 重启 Klipper 服务
sudo systemctl restart klipper
```

## 代码架构

### 核心文件

**klipper/klippy/extras/trsync_adaptive.py**
- `TRSyncAdaptive` 类：实现自适应超时算法
- `_get_rtt()`: 从 MCU clocksync 获取当前 RTT
- `update()`: 使用 EWMA 算法更新 RTT 统计
- `get_timeout()`: 计算当前超时值

**klipper/klippy/mcu.py**
- 修改 `MCU_trsync` 类以支持 adaptive timeout 模式
- 在 `Printer` 类中添加 `trsync_timeout_mode` 配置支持
- 集成 `TRSyncAdaptive` 模块

### EWMA 算法实现

```python
# 更新平均值
diff = rtt - rtt_avg
rtt_avg += alpha * diff

# 更新方差
rtt_var += alpha * (diff * diff - rtt_var)

# 计算超时
timeout = clamp(
    rtt_avg + sigma_multiplier * sqrt(rtt_var) + margin,
    min_timeout,
    max_timeout
)
```

**关键参数**：
- `alpha` (0.2): EWMA 平滑系数，越小越平滑
- `sigma_multiplier` (4.0): 标准差倍数，4.0 对应 99.99% 置信度
- `margin` (0.008s): Linux 调度余量
- `min_timeout` (0.025s): 最小超时保护
- `max_timeout` (0.120s): 最大超时保护

### 测试架构

**test_trsync_adaptive.py**
- Mock 对象：`MockConfig`, `MockPrinter`, `MockClockSync`, `MockMCU`
- 测试用例：
  - EWMA 算法正确性
  - 超时上下限约束
  - RTT 不可用时的 fallback
  - 典型使用场景（不同 RTT 值）
  - 方差计算正确性

## 配置说明

在 `printer.cfg` 的 `[printer]` 段添加：

```ini
[printer]
trsync_timeout_mode: adaptive    # 启用自适应模式（默认 fixed）
trsync_min_timeout: 0.025        # 最小超时 25ms
trsync_max_timeout: 0.120        # 最大超时 120ms
trsync_margin: 0.008             # 调度余量 8ms
trsync_sigma_multiplier: 4.0     # 标准差倍数
trsync_ewma_alpha: 0.2           # EWMA 平滑系数
```

## 开发注意事项

### 修改代码时
1. 保持与 Klipper 代码风格一致（参考现有代码）
2. 所有浮点数计算使用秒为单位
3. 添加适当的日志记录（logging.info/debug/warning）
4. 更新单元测试以覆盖新功能

### 修改算法参数时
1. 更新 `test_trsync_adaptive.py` 中的预期值
2. 运行测试确保所有场景通过
3. 更新 README.md 中的典型效果表格

### 生成新的 patch 文件
```bash
# 在 Klipper 目录中
cd ~/klipper

# 生成 patch（假设修改已提交到 git）
git diff HEAD~1 > ~/klipper_trsync_patch/klipper_trsync_adaptive.patch

# 或者对比特定文件
git diff klippy/mcu.py klippy/extras/trsync_adaptive.py > patch_file.patch
```

## 安全设计

1. **默认关闭**：`trsync_timeout_mode` 默认为 `fixed`，保持原始行为
2. **Fallback 机制**：RTT 不可用时返回 `min_timeout`
3. **上下限保护**：防止计算出的超时值过小或过大
4. **参数验证**：所有配置参数都有 minval/maxval 限制

## 兼容性

- **Klipper 版本**：v0.11.0 及以上
- **Python 版本**：Python 3.x
- **MCU 固件**：无需修改，完全兼容现有固件
- **配置文件**：向后兼容，不影响未启用 adaptive 模式的机器
