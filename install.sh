#!/bin/bash
# Klipper TRSYNC Timeout Fix 安装脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印函数
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否以 root 运行
if [ "$EUID" -eq 0 ]; then
    print_error "请不要以 root 用户运行此脚本"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 默认 Klipper 路径
KLIPPER_PATH="${HOME}/klipper"
# 默认使用简易模式
INSTALL_MODE="simple"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --klipper-path)
            KLIPPER_PATH="$2"
            shift 2
            ;;
        --mode)
            INSTALL_MODE="$2"
            shift 2
            ;;
        --help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --klipper-path PATH    指定 Klipper 安装路径 (默认: ~/klipper)"
            echo "  --mode MODE            安装模式: simple 或 adaptive (默认: simple)"
            echo "                         simple: 直接修改固定超时值 (稳定，推荐)"
            echo "                         adaptive: 自适应超时算法 (实验性)"
            echo "  --help                 显示此帮助信息"
            exit 0
            ;;
        *)
            print_error "未知选项: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
done

if [ "$INSTALL_MODE" != "simple" ] && [ "$INSTALL_MODE" != "adaptive" ]; then
    print_error "无效的模式: $INSTALL_MODE (只能是 simple 或 adaptive)"
    exit 1
fi

print_info "Klipper TRSYNC Timeout Fix 安装脚本 - 模式: $INSTALL_MODE"
echo ""

# 检查 Klipper 路径
if [ ! -d "$KLIPPER_PATH" ]; then
    print_error "Klipper 路径不存在: $KLIPPER_PATH"
    print_info "请使用 --klipper-path 指定正确的路径"
    exit 1
fi

if [ ! -f "$KLIPPER_PATH/klippy/klippy.py" ]; then
    print_error "无效的 Klipper 安装: $KLIPPER_PATH"
    exit 1
fi

print_info "找到 Klipper 安装: $KLIPPER_PATH"

# 备份原始文件
BACKUP_FILE="$KLIPPER_PATH/klippy/mcu.py.backup_$(date +%Y%m%d_%H%M%S)"
cp "$KLIPPER_PATH/klippy/mcu.py" "$BACKUP_FILE"
print_info "已备份: $BACKUP_FILE"

if [ "$INSTALL_MODE" = "simple" ]; then
    # 简易模式：直接修改固定超时值
    print_info "简易模式：修改 TRSYNC_TIMEOUT 从 0.025 到 0.050"
    sed -i 's/^TRSYNC_TIMEOUT = 0\.025$/TRSYNC_TIMEOUT = 0.050/' "$KLIPPER_PATH/klippy/mcu.py"

    if grep -q "^TRSYNC_TIMEOUT = 0.050$" "$KLIPPER_PATH/klippy/mcu.py"; then
        print_info "修改成功"
    else
        print_error "修改失败，请检查文件"
        exit 1
    fi
else
    # 自适应模式：安装完整的 adaptive timeout 模块
    print_info "自适应模式：安装 adaptive timeout 模块"

    BACKUP_DIR="$KLIPPER_PATH/klippy/.backup_trsync_adaptive_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    cp "$BACKUP_FILE" "$BACKUP_DIR/mcu.py"

    cp "$SCRIPT_DIR/klipper/klippy/extras/trsync_adaptive.py" \
       "$KLIPPER_PATH/klippy/extras/trsync_adaptive.py"
    print_info "已安装: trsync_adaptive.py"

    cp "$SCRIPT_DIR/klipper/klippy/mcu.py" \
       "$KLIPPER_PATH/klippy/mcu.py"
    print_info "已安装: mcu.py"

    print_warn "需要手动配置 printer.cfg"
    print_info "请在 [trsync_adaptive] 段添加以下配置："
    echo ""
    echo "  [trsync_adaptive]"
    echo "  trsync_min_timeout: 0.025"
    echo "  trsync_max_timeout: 0.120"
    echo "  trsync_margin: 0.008"
    echo "  trsync_sigma_multiplier: 4.0"
    echo "  trsync_ewma_alpha: 0.2"
    echo ""
fi

# 重启 Klipper
echo ""
read -p "是否立即重启 Klipper 服务? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "重启 Klipper 服务..."
    sudo systemctl restart klipper
    sleep 2

    if systemctl is-active --quiet klipper; then
        print_info "Klipper 服务已成功重启"
    else
        print_error "Klipper 服务启动失败，请检查日志:"
        echo "  journalctl -u klipper -n 50"
        exit 1
    fi
else
    print_warn "请稍后手动重启 Klipper:"
    echo "  sudo systemctl restart klipper"
fi

echo ""
print_info "安装完成！"
echo ""

if [ "$INSTALL_MODE" = "simple" ]; then
    print_info "TRSYNC 超时已从 25ms 增加到 50ms (简易模式)"
    echo ""
    print_info "如需回退:"
    echo "  cp $BACKUP_FILE $KLIPPER_PATH/klippy/mcu.py"
    echo "  sudo systemctl restart klipper"
else
    print_info "自适应超时模块已安装 (实验性)"
    echo ""
    print_info "后续步骤:"
    echo "  1. 编辑 printer.cfg 添加 [trsync_adaptive] 配置段"
    echo "  2. 重启 Klipper (如果尚未重启)"
    echo "  3. 测试 Z homing: G28 Z"
    echo "  4. 查看日志: tail -f /tmp/klippy.log | grep -i trsync"
    echo ""
    print_info "如需回退:"
    echo "  cp $BACKUP_FILE $KLIPPER_PATH/klippy/mcu.py"
    echo "  rm $KLIPPER_PATH/klippy/extras/trsync_adaptive.py"
    echo "  sudo systemctl restart klipper"
fi
