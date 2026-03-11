#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Klipper TRSYNC Adaptive Timeout 单元测试

测试 EWMA 算法、timeout 计算和边界条件
"""

import sys
import os
import math

# 添加 klippy 路径
klippy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'klipper/klippy')
sys.path.insert(0, klippy_path)

class MockConfig:
    """模拟 Klipper config 对象"""
    def __init__(self, params):
        self.params = params
        self.printer = MockPrinter()

    def get_printer(self):
        return self.printer

    def getfloat(self, name, default=None, minval=None, maxval=None):
        value = self.params.get(name, default)
        if minval is not None and value < minval:
            raise ValueError(f"{name} below minimum")
        if maxval is not None and value > maxval:
            raise ValueError(f"{name} above maximum")
        return value

class MockPrinter:
    """模拟 Klipper printer 对象"""
    pass

class MockClockSync:
    """模拟 ClockSync 对象"""
    def __init__(self, min_half_rtt=0.005):
        self.min_half_rtt = min_half_rtt

class MockMCU:
    """模拟 MCU 对象"""
    def __init__(self, name='mcu', rtt=0.005):
        self.name = name
        self._clocksync = MockClockSync(rtt)

    def get_name(self):
        return self.name

    def set_rtt(self, rtt):
        self._clocksync.min_half_rtt = rtt

def test_ewma_algorithm():
    """测试 EWMA 算法正确性"""
    print("测试 1: EWMA 算法")

    from extras import trsync_adaptive

    config = MockConfig({
        'trsync_min_timeout': 0.025,
        'trsync_max_timeout': 0.120,
        'trsync_margin': 0.008,
        'trsync_sigma_multiplier': 4.0,
        'trsync_ewma_alpha': 0.2,
    })

    mcu = MockMCU('test_mcu', rtt=0.010)
    adaptive = trsync_adaptive.TRSyncAdaptive(config, mcu)

    # 首次更新
    adaptive.update()
    assert adaptive.initialized, "应该已初始化"
    assert abs(adaptive.rtt_avg - 0.010) < 1e-6, f"首次 RTT 应为 0.010，实际 {adaptive.rtt_avg}"

    # 模拟 RTT 变化
    mcu.set_rtt(0.012)
    adaptive.update()

    # 验证 EWMA 更新
    expected_avg = 0.010 + 0.2 * (0.012 - 0.010)
    assert abs(adaptive.rtt_avg - expected_avg) < 1e-6, \
        f"EWMA 平均值错误: 期望 {expected_avg}, 实际 {adaptive.rtt_avg}"

    print("  ✓ EWMA 算法正确")

def test_timeout_bounds():
    """测试 timeout 上下限约束"""
    print("测试 2: Timeout 上下限")

    from extras import trsync_adaptive

    config = MockConfig({
        'trsync_min_timeout': 0.025,
        'trsync_max_timeout': 0.120,
        'trsync_margin': 0.008,
        'trsync_sigma_multiplier': 4.0,
        'trsync_ewma_alpha': 0.2,
    })

    # 测试下限
    mcu = MockMCU('test_mcu', rtt=0.001)  # 极小 RTT
    adaptive = trsync_adaptive.TRSyncAdaptive(config, mcu)
    adaptive.update()
    timeout = adaptive.get_timeout()
    assert timeout >= 0.025, f"Timeout 应不低于 min_timeout，实际 {timeout}"
    print(f"  ✓ 下限保护正常: RTT=0.001s -> timeout={timeout:.6f}s (>= 0.025s)")

    # 测试上限
    mcu = MockMCU('test_mcu', rtt=0.100)  # 极大 RTT
    adaptive = trsync_adaptive.TRSyncAdaptive(config, mcu)
    adaptive.update()
    timeout = adaptive.get_timeout()
    assert timeout <= 0.120, f"Timeout 应不高于 max_timeout，实际 {timeout}"
    print(f"  ✓ 上限保护正常: RTT=0.100s -> timeout={timeout:.6f}s (<= 0.120s)")

def test_rtt_unavailable():
    """测试 RTT 不可用时的 fallback"""
    print("测试 3: RTT 不可用 Fallback")

    from extras import trsync_adaptive

    config = MockConfig({
        'trsync_min_timeout': 0.025,
        'trsync_max_timeout': 0.120,
        'trsync_margin': 0.008,
        'trsync_sigma_multiplier': 4.0,
        'trsync_ewma_alpha': 0.2,
    })

    mcu = MockMCU('test_mcu', rtt=999999999.9)  # 无效 RTT
    adaptive = trsync_adaptive.TRSyncAdaptive(config, mcu)
    adaptive.update()

    # 未初始化时应返回 min_timeout
    timeout = adaptive.get_timeout()
    assert timeout == 0.025, f"RTT 不可用时应返回 min_timeout，实际 {timeout}"
    print(f"  ✓ Fallback 正常: 无效 RTT -> timeout={timeout:.6f}s (= min_timeout)")

def test_typical_scenarios():
    """测试典型使用场景"""
    print("测试 4: 典型场景")

    from extras import trsync_adaptive

    config = MockConfig({
        'trsync_min_timeout': 0.025,
        'trsync_max_timeout': 0.120,
        'trsync_margin': 0.008,
        'trsync_sigma_multiplier': 4.0,
        'trsync_ewma_alpha': 0.2,
    })

    scenarios = [
        (0.005, "Single MCU / USB"),
        (0.008, "Multi-MCU USB"),
        (0.012, "Multi-MCU + CAN (轻度)"),
        (0.020, "Multi-MCU + CAN (高负载)"),
    ]

    for rtt, desc in scenarios:
        mcu = MockMCU('test_mcu', rtt=rtt)
        adaptive = trsync_adaptive.TRSyncAdaptive(config, mcu)

        # 模拟多次更新以稳定 EWMA
        for _ in range(10):
            adaptive.update()

        timeout = adaptive.get_timeout()
        print(f"  ✓ {desc}: RTT={rtt*1000:.1f}ms -> timeout={timeout*1000:.1f}ms")

def test_variance_calculation():
    """测试方差计算"""
    print("测试 5: 方差计算")

    from extras import trsync_adaptive

    config = MockConfig({
        'trsync_min_timeout': 0.025,
        'trsync_max_timeout': 0.120,
        'trsync_margin': 0.008,
        'trsync_sigma_multiplier': 4.0,
        'trsync_ewma_alpha': 0.2,
    })

    mcu = MockMCU('test_mcu', rtt=0.010)
    adaptive = trsync_adaptive.TRSyncAdaptive(config, mcu)

    # 模拟稳定的 RTT
    for _ in range(20):
        adaptive.update()

    std_stable = math.sqrt(max(adaptive.rtt_var, 0.))

    # 模拟波动的 RTT
    for i in range(20):
        mcu.set_rtt(0.010 + 0.005 * (i % 2))  # 在 10ms 和 15ms 之间波动
        adaptive.update()

    std_volatile = math.sqrt(max(adaptive.rtt_var, 0.))

    assert std_volatile > std_stable, "波动 RTT 的标准差应大于稳定 RTT"
    print(f"  ✓ 方差计算正确: 稳定 std={std_stable*1000:.3f}ms, "
          f"波动 std={std_volatile*1000:.3f}ms")

def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Klipper TRSYNC Adaptive Timeout 单元测试")
    print("=" * 60)
    print()

    try:
        test_ewma_algorithm()
        test_timeout_bounds()
        test_rtt_unavailable()
        test_typical_scenarios()
        test_variance_calculation()

        print()
        print("=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"✗ 测试失败: {e}")
        print("=" * 60)
        return 1

    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return 1

if __name__ == '__main__':
    sys.exit(run_all_tests())
