#!/usr/bin/env bash
# Своп и настройки памяти для серверов сетки (1 ГБ RAM, ~20 сайтов WordPress).
#
# Запускать от root на каждом сервере:
#     bash setup_swap.sh              # своп 2 ГБ
#     SWAP_GB=3 bash setup_swap.sh    # другой размер
#     DRY_RUN=1 bash setup_swap.sh    # только показать, что будет сделано
#
# Скрипт идемпотентен: существующий своп не трогает, в fstab не дублирует.

set -euo pipefail

SWAP_GB="${SWAP_GB:-2}"
SWAPFILE="${SWAPFILE:-/swapfile}"
DRY_RUN="${DRY_RUN:-0}"
MIN_FREE_GB="${MIN_FREE_GB:-4}"   # столько ГБ должно остаться свободными помимо свопа

say()  { printf '%s\n' "$*"; }
run()  { if [ "$DRY_RUN" = "1" ]; then say "  [показ] $*"; else eval "$@"; fi; }
fail() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "нужны права root"

say "=== Память и диск до изменений ==="
free -h || true
df -h / | tail -1
say ""

# --- уже есть своп? ---
current_swap_kb=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
if [ "${current_swap_kb:-0}" -gt 0 ]; then
    say "Своп уже подключён ($((current_swap_kb / 1024)) МБ). Файл создавать не буду."
    swapon --show || true
    SKIP_CREATE=1
else
    SKIP_CREATE=0
fi

if [ "$SKIP_CREATE" = "0" ]; then
    # --- хватает ли места на диске ---
    avail_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
    need_gb=$((SWAP_GB + MIN_FREE_GB))
    say "Свободно на /: ${avail_gb} ГБ, требуется ${need_gb} ГБ (своп ${SWAP_GB} + запас ${MIN_FREE_GB})"
    [ "$avail_gb" -ge "$need_gb" ] || fail "недостаточно места; уменьшите SWAP_GB или освободите диск"

    if [ -e "$SWAPFILE" ]; then
        fail "$SWAPFILE уже существует, но не активен — разберитесь вручную"
    fi

    say ""
    say "=== Создаю своп ${SWAP_GB} ГБ в $SWAPFILE ==="
    # fallocate быстрее, но на некоторых ФС даёт дырявый файл — тогда dd
    if fallocate -l "${SWAP_GB}G" "$SWAPFILE" 2>/dev/null; then
        say "  файл создан через fallocate"
    else
        say "  fallocate недоступен, использую dd (это дольше)"
        run "dd if=/dev/zero of=$SWAPFILE bs=1M count=$((SWAP_GB * 1024)) status=none"
    fi
    run "chmod 600 $SWAPFILE"
    run "mkswap $SWAPFILE >/dev/null"
    run "swapon $SWAPFILE"
    say "  своп включён"

    # --- fstab, чтобы пережил перезагрузку ---
    if grep -qs "^[^#]*$SWAPFILE" /etc/fstab; then
        say "  запись в /etc/fstab уже есть"
    else
        run "cp /etc/fstab /etc/fstab.bak.\$(date +%Y%m%d%H%M%S)"
        run "printf '%s none swap sw 0 0\n' '$SWAPFILE' >> /etc/fstab"
        say "  запись в /etc/fstab добавлена (бэкап рядом)"
    fi
fi

# --- параметры ядра ---
# swappiness=10: своп только как подушка при пиках, а не постоянное вытеснение
# vfs_cache_pressure=50: дольше держим кеш inode/dentry, меньше дисковых обращений
say ""
say "=== Параметры памяти ==="
SYSCTL_FILE=/etc/sysctl.d/99-pbn-memory.conf
if [ -f "$SYSCTL_FILE" ]; then
    say "  $SYSCTL_FILE уже есть, перезаписываю"
fi
if [ "$DRY_RUN" = "1" ]; then
    say "  [показ] записать vm.swappiness=10 и vm.vfs_cache_pressure=50 в $SYSCTL_FILE"
else
    cat > "$SYSCTL_FILE" <<'EOF'
# Сетка PBN: своп как подушка на пиках, не как постоянное вытеснение
vm.swappiness=10
vm.vfs_cache_pressure=50
EOF
    sysctl -p "$SYSCTL_FILE" >/dev/null
    say "  применено: swappiness=10, vfs_cache_pressure=50"
fi

say ""
say "=== Память и диск после изменений ==="
free -h || true
df -h / | tail -1
say ""
say "Готово."
say ""
say "Что стоит проверить дальше (память на 1 ГБ уходит в основном сюда):"
say "  • один общий пул PHP-FPM на все сайты, а не по пулу на сайт;"
say "    pm = ondemand, pm.max_children 5-6, pm.process_idle_timeout 10s"
say "  • MariaDB: innodb_buffer_pool_size = 128M, performance_schema = off,"
say "    max_connections = 30"
say "  • статическое кеширование в nginx, чтобы обходы ботов не будили PHP"
say ""
say "Текущее потребление по процессам:"
ps -eo rss,comm --sort=-rss 2>/dev/null | head -12 | awk 'NR==1{print "  RSS(КБ)  ПРОЦЕСС"} NR>1{printf "  %8d  %s\n", $1, $2}'
