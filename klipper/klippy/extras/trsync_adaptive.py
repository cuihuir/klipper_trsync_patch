# Adaptive TRSYNC timeout calculation
#
# Copyright (C) 2024  Your Name <your@email.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging, math

# 全局配置存储
_trsync_adaptive_configs = {}

class TRSyncAdaptive:
    """
    动态计算 TRSYNC timeout，基于实时 RTT 测量
    使用 EWMA (指数加权移动平均) 算法平滑 RTT 波动
    """
    def __init__(self, config_or_dict, mcu):
        self.mcu = mcu
        self.printer = mcu.get_printer()

        # 支持两种初始化方式：config 对象或配置字典
        if hasattr(config_or_dict, 'getfloat'):
            # 旧方式：从 config 对象读取
            config = config_or_dict
            self.min_timeout = config.getfloat('trsync_min_timeout', 0.025,
                                               minval=0.010, maxval=0.500)
            self.max_timeout = config.getfloat('trsync_max_timeout', 0.120,
                                               minval=0.050, maxval=1.000)
            self.margin = config.getfloat('trsync_margin', 0.008,
                                          minval=0.000, maxval=0.100)
            self.sigma_mult = config.getfloat('trsync_sigma_multiplier', 4.0,
                                              minval=1.0, maxval=10.0)
            self.alpha = config.getfloat('trsync_ewma_alpha', 0.2,
                                         minval=0.01, maxval=1.0)
        else:
            # 新方式：从配置字典读取
            config_dict = config_or_dict
            self.min_timeout = config_dict['min_timeout']
            self.max_timeout = config_dict['max_timeout']
            self.margin = config_dict['margin']
            self.sigma_mult = config_dict['sigma_multiplier']
            self.alpha = config_dict['ewma_alpha']

        # EWMA 状态变量
        self.rtt_avg = 0.
        self.rtt_var = 0.
        self.initialized = False

        logging.info("TRSyncAdaptive initialized for MCU '%s': "
                     "min=%.3f max=%.3f margin=%.3f sigma_mult=%.1f alpha=%.2f",
                     mcu.get_name(), self.min_timeout, self.max_timeout,
                     self.margin, self.sigma_mult, self.alpha)

    def _get_rtt(self):
        """从 MCU clocksync 获取当前 RTT (单程时间)"""
        try:
            clocksync = self.mcu._clocksync
            if clocksync is None:
                return None
            # min_half_rtt 是单程时间，单位是秒
            rtt = clocksync.min_half_rtt
            if rtt > 0 and rtt < 999999999.0:
                return rtt
        except Exception as e:
            logging.warning("Failed to get RTT from MCU '%s': %s",
                           self.mcu.get_name(), str(e))
        return None

    def update(self):
        """更新 RTT 统计信息 (EWMA 算法)"""
        rtt = self._get_rtt()
        if rtt is None:
            return

        if not self.initialized:
            # 首次初始化
            self.rtt_avg = rtt
            self.rtt_var = (rtt * 0.1) ** 2  # 初始方差设为 10% RTT
            self.initialized = True
            logging.info("TRSyncAdaptive first RTT for MCU '%s': %.6f s",
                        self.mcu.get_name(), rtt)
        else:
            # EWMA 更新
            diff = rtt - self.rtt_avg
            self.rtt_avg += self.alpha * diff
            self.rtt_var += self.alpha * (diff * diff - self.rtt_var)

    def get_timeout(self):
        """计算当前的 timeout 值"""
        if not self.initialized:
            # 如果还没有 RTT 数据，返回最小 timeout
            logging.warning("TRSyncAdaptive not initialized for MCU '%s', "
                           "using min_timeout", self.mcu.get_name())
            return self.min_timeout

        # 计算标准差
        std = math.sqrt(max(self.rtt_var, 0.))

        # 计算 timeout: RTT_avg + sigma_mult * std + margin
        timeout = self.rtt_avg + self.sigma_mult * std + self.margin

        # 应用上下限
        timeout = max(timeout, self.min_timeout)
        timeout = min(timeout, self.max_timeout)

        logging.debug("TRSyncAdaptive timeout for MCU '%s': "
                     "rtt_avg=%.6f std=%.6f timeout=%.6f",
                     self.mcu.get_name(), self.rtt_avg, std, timeout)

        return timeout

def load_config(config):
    """Klipper 模块加载入口 - 支持 [trsync_adaptive] 配置段"""
    # 这里读取并验证配置参数，但实际的 TRSyncAdaptive 对象由 TriggerDispatch 创建

    # 读取并验证参数（让 Klipper 知道这些参数是有效的）
    min_timeout = config.getfloat('trsync_min_timeout', 0.025,
                                  minval=0.010, maxval=0.500)
    max_timeout = config.getfloat('trsync_max_timeout', 0.120,
                                  minval=0.050, maxval=1.000)
    margin = config.getfloat('trsync_margin', 0.008,
                            minval=0.000, maxval=0.100)
    sigma_mult = config.getfloat('trsync_sigma_multiplier', 4.0,
                                minval=1.0, maxval=10.0)
    alpha = config.getfloat('trsync_ewma_alpha', 0.2,
                           minval=0.01, maxval=1.0)

    # 将参数存储在全局字典中，供 TriggerDispatch 使用
    trsync_config = {
        'min_timeout': min_timeout,
        'max_timeout': max_timeout,
        'margin': margin,
        'sigma_multiplier': sigma_mult,
        'ewma_alpha': alpha
    }
    _trsync_adaptive_configs['default'] = trsync_config

    logging.info("TRSyncAdaptive config section loaded: min=%.3f max=%.3f margin=%.3f sigma=%.1f alpha=%.2f",
                 min_timeout, max_timeout, margin, sigma_mult, alpha)
    return None
