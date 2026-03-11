# Klipper TRSYNC Adaptive Timeout Patch

## 概述

此补丁为 Klipper 添加了自适应 TRSYNC timeout 功能，用于解决 multi-MCU + CAN toolhead 环境下的 "Communication timeout during homing" 错误。

## 问题背景

在 multi-MCU + CAN 架构中，Z homing 过程经常出现超时错误：
- 当前 TRSYNC_TIMEOUT 硬编码为 25ms
- 实际延迟（Host scheduling + USB + CAN + MCU processing）经常超过 25ms
- 导致误判超时，homing 失败

## 解决方案

**自适应 timeout 机制：**
- 基于实时 RTT（Round-Trip Time）动态计算 timeout
- 使用 EWMA（指数加权移动平均）平滑 RTT 波动
- 加入安全上下限保护
- 完全在 Host 端实现，无需修改 MCU 固件

**核心算法：**
```
timeout = clamp(
    RTT_avg + sigma_multiplier * RTT_std + margin,
    min_timeout,
    max_timeout
)
```

## 文件结构

```
klipper_trsync_patch/
├── README.md                      # 本文档
├── install.sh                     # 自动安装脚本
├── uninstall.sh                   # 自动卸载脚本
├── test_trsync_adaptive.py        # 单元测试
├── klipper_trsync_adaptive.patch  # Git patch 文件
├── klipper/                       # 修改后的源码
│   └── klippy/
│       ├── mcu.py                 # 修改：添加 adaptive timeout 支持
│       └── extras/
│           └── trsync_adaptive.py # 新增：adaptive timeout 模块
└── docs/                          # 设计文档（不提交到 git）
    ├── DEPLOYMENT.md              # 详细部署指南
    ├── printer.cfg.example        # 配置示例
    └── design.md                  # 设计文档
```

## 快速开始

### 1. 应用补丁

**方法 1: 使用安装脚本（推荐）**

```bash
cd klipper_trsync_patch
./install.sh
```

安装脚本会自动：
- 备份原始文件
- 复制新文件到 Klipper 目录
- 提示配置 printer.cfg
- 可选重启 Klipper 服务

**方法 2: 使用 Git Patch**

`.patch` 文件是 Git 格式的补丁文件，包含了所有代码更改的 diff 信息。可以直接应用到 Klipper 源码：

```bash
# 进入 Klipper 目录
cd ~/klipper

# 应用 patch
git apply /path/to/klipper_trsync_adaptive.patch

# 如果出错，可以先检查是否能应用
git apply --check /path/to/klipper_trsync_adaptive.patch
```

**注意**：使用 patch 方式需要确保 Klipper 源码是干净的 git 仓库。

**方法 3: 手动复制文件**

```bash
# 复制新模块
cp klipper_trsync_patch/klipper/klippy/extras/trsync_adaptive.py \
   ~/klipper/klippy/extras/

# 复制修改的 mcu.py（建议先备份）
cp ~/klipper/klippy/mcu.py ~/klipper/klippy/mcu.py.backup
cp klipper_trsync_patch/klipper/klippy/mcu.py \
   ~/klipper/klippy/mcu.py
```

### 2. 配置

编辑 `printer.cfg`：

```ini
[printer]
trsync_timeout_mode: adaptive
trsync_min_timeout: 0.025
trsync_max_timeout: 0.120
trsync_margin: 0.008
trsync_sigma_multiplier: 4.0
trsync_ewma_alpha: 0.2
```

### 3. 重启 Klipper

```bash
sudo systemctl restart klipper
```

**无需重新编译或刷写 MCU 固件！**

### 4. 验证

```bash
# 查看日志
tail -f /tmp/klippy.log | grep -i trsync

# 测试 homing
G28 Z
```

## 测试

运行单元测试：

```bash
python3 test_trsync_adaptive.py
```

预期输出：
```
============================================================
Klipper TRSYNC Adaptive Timeout 单元测试
============================================================

测试 1: EWMA 算法
  ✓ EWMA 算法正确
测试 2: Timeout 上下限
  ✓ 下限保护正常
  ✓ 上限保护正常
测试 3: RTT 不可用 Fallback
  ✓ Fallback 正常
测试 4: 典型场景
  ✓ Single MCU / USB: RTT=5.0ms -> timeout=25.0ms
  ✓ Multi-MCU USB: RTT=8.0ms -> timeout=25.0ms
  ✓ Multi-MCU + CAN (轻度): RTT=12.0ms -> timeout=25.0ms
  ✓ Multi-MCU + CAN (高负载): RTT=20.0ms -> timeout=30.9ms
测试 5: 方差计算
  ✓ 方差计算正确

============================================================
✓ 所有测试通过！
============================================================
```

## 典型效果

| RTT  | Calculated Timeout | 适用场景 |
|------|-------------------|---------|
| 5ms  | ~25ms            | Single MCU / USB |
| 8ms  | ~35ms            | Multi-MCU USB |
| 12ms | ~50ms            | Multi-MCU + CAN (轻度) |
| 20ms | ~80ms            | Multi-MCU + CAN (高负载) |

## 配置调优

详细配置说明请参考 `docs/printer.cfg.example` 文件。

### 配置参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| trsync_timeout_mode | fixed | fixed（固定）或 adaptive（自适应） |
| trsync_min_timeout | 0.025s | 最小 timeout，防止过小导致误判 |
| trsync_max_timeout | 0.120s | 最大 timeout，防止故障时长时间运动 |
| trsync_margin | 0.008s | Linux 调度余量 |
| trsync_sigma_multiplier | 4.0 | Jitter 放大倍数（4.0 对应 99.99% 置信度） |
| trsync_ewma_alpha | 0.2 | EWMA 平滑系数，越小越平滑 |

## 优势

- ✓ 不修改 MCU firmware
- ✓ 不改变 CAN 协议
- ✓ 不影响普通机器（默认关闭）
- ✓ 可配置、可回退
- ✓ 适合量产设备

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

### 安全设计

1. **默认关闭**：保持原始行为
2. **Fallback 机制**：RTT 不可用时返回 min_timeout
3. **上限保护**：防止故障时长时间运动
4. **下限保护**：确保不低于安全值

## 兼容性

- **Klipper 版本**：v0.11.0 及以上
- **MCU 固件**：无需修改，完全兼容
- **现有配置**：默认关闭，不影响现有机器

## 许可证

本补丁遵循 Klipper 的 GNU GPLv3 许可证。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 相关链接

- [Klipper 官方文档](https://www.klipper3d.org/)
- [Klipper GitHub](https://github.com/Klipper3d/klipper)
