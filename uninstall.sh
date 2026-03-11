#!/bin/bash
# Klipper TRSYNC Adaptive Timeout 卸载脚本

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

# 默认 Klipper 路径
KLIPPER_PATH="${HOME}/klipper"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --klipper-path)
            KLIPPER_PATH="$2"
            shift 2
            ;;
        --help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --klipper-path PATH    指定 Klipper 安装路径 (默认: ~/klipper)"
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

print_info "Klipper TRSYNC Adaptive Timeout 卸载脚本"
echo ""

# 检查 Klipper 路径
if [ ! -d "$KLIPPER_PATH" ]; then
    print_error "Klipper 路径不存在: $KLIPPER_PATH"
    exit 1
fi

print_info "找到 Klipper 安装: $KLIPPER_PATH"

# 查找最新的备份
BACKUP_DIRS=("$KLIPPER_PATH/klippy/.backup_trsync_adaptive_"*)
if [ ${#BACKUP_DIRS[@]} -eq 0 ] || [ ! -d "${BACKUP_DIRS[0]}" ]; then
    print_error "未找到备份文件"
    print_info "请手动从 Klipper 官方仓库恢复 mcu.py"
    exit 1
fi

# 使用最新的备份
LATEST_BACKUP=$(ls -td "$KLIPPER_PATH/klippy/.backup_trsync_adaptive_"* | head -1)
print_info "找到备份: $LATEST_BACKUP"

# 确认卸载
echo ""
print_warn "此操作将:"
echo "  1. 删除 trsync_adaptive.py"
echo "  2. 从备份恢复 mcu.py"
echo "  3. 重启 Klipper 服务"
echo ""
read -p "确认继续? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "已取消"
    exit 0
fi

# 删除 trsync_adaptive.py
print_info "删除 trsync_adaptive.py..."
rm -f "$KLIPPER_PATH/klippy/extras/trsync_adaptive.py"
rm -f "$KLIPPER_PATH/klippy/extras/trsync_adaptive.pyc"

# 恢复 mcu.py
print_info "恢复 mcu.py..."
cp "$LATEST_BACKUP/mcu.py" "$KLIPPER_PATH/klippy/mcu.py"

# 重启 Klipper
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

echo ""
print_info "卸载完成！"
echo ""
print_warn "请记得从 printer.cfg 中删除 adaptive timeout 相关配置:"
echo "  trsync_timeout_mode"
echo "  trsync_min_timeout"
echo "  trsync_max_timeout"
echo "  trsync_margin"
echo "  trsync_sigma_multiplier"
echo "  trsync_ewma_alpha"
