#!/usr/bin/env bash
# Закрывает 80 и 443 для всех, кроме Cloudflare.
#
#     bash lock_origin.sh status
#     bash lock_origin.sh install --dry-run
#     bash lock_origin.sh install
#     bash lock_origin.sh remove
#
# ЗАПУСКАТЬ ТОЛЬКО ПОСЛЕ ТОГО, КАК ДОМЕНЫ ПОЕХАЛИ ЧЕРЕЗ CLOUDFLARE.
# Пока неймсерверы не сменились, это отрежет единственный способ проверить
# сайты снаружи.
#
# Зачем это вообще: открытый origin выдаёт настоящий IP, а на нём стоят все 20
# сайтов сразу — то есть он их прямо связывает между собой. Раньше на прежних
# серверах 80/443 были закрыты ровно так же.
#
# Порт 22 не трогается: правило висит отдельной таблицей с политикой accept и
# фильтрует только веб-порты. Остаться без SSH этим скриптом нельзя.

set -uo pipefail

MODE="${1:-status}"
DRY=0
[ "${2:-}" = "--dry-run" ] && DRY=1
TABLE="pbn_origin"

[ "$(id -u)" -eq 0 ] || { echo "нужны права root" >&2; exit 1; }

case "$MODE" in
    status)
        if nft list table inet "$TABLE" >/dev/null 2>&1; then
            echo "origin закрыт, правила:"
            nft list table inet "$TABLE"
        else
            echo "origin открыт всему интернету — таблицы inet $TABLE нет"
        fi
        exit 0
        ;;
    remove)
        nft delete table inet "$TABLE" 2>/dev/null && echo "правила сняты, origin снова открыт" \
            || echo "правил и не было"
        exit 0
        ;;
    install) ;;
    *) echo "использование: bash lock_origin.sh status|install|remove [--dry-run]" >&2; exit 1 ;;
esac

V4=$(curl -s --max-time 30 https://www.cloudflare.com/ips-v4)
V6=$(curl -s --max-time 30 https://www.cloudflare.com/ips-v6)
if [ -z "$V4" ]; then
    echo "ОШИБКА: не получил список адресов Cloudflare — правила не ставлю" >&2
    exit 1
fi
N4=$(printf '%s\n' "$V4" | grep -c '/')
N6=$(printf '%s\n' "$V6" | grep -c '/' || true)
echo "диапазонов Cloudflare: IPv4 $N4, IPv6 $N6"
if [ "$N4" -lt 5 ]; then
    echo "ОШИБКА: список подозрительно короткий, правила не ставлю" >&2
    exit 1
fi

SET4=$(printf '%s\n' "$V4" | grep '/' | paste -sd, -)
SET6=$(printf '%s\n' "$V6" | grep '/' | paste -sd, -)

RULES=$(cat <<NFT
table inet $TABLE {
    set cf4 {
        type ipv4_addr
        flags interval
        elements = { $SET4 }
    }
    set cf6 {
        type ipv6_addr
        flags interval
        elements = { $SET6 }
    }
    chain input {
        type filter hook input priority filter; policy accept;
        iif lo accept
        tcp dport { 80, 443 } ip saddr @cf4 accept
        tcp dport { 80, 443 } ip6 saddr @cf6 accept
        tcp dport { 80, 443 } drop
    }
}
NFT
)

if [ "$DRY" = "1" ]; then
    echo "--- правила, которые будут поставлены (ничего не менял) ---"
    printf '%s\n' "$RULES"
    exit 0
fi

nft delete table inet "$TABLE" 2>/dev/null
printf '%s\n' "$RULES" > /tmp/pbn_origin.nft
if ! nft -f /tmp/pbn_origin.nft; then
    echo "ОШИБКА: nft не принял правила, origin остался открыт" >&2
    exit 1
fi

mkdir -p /etc/nftables.d
cp /tmp/pbn_origin.nft /etc/nftables.d/pbn_origin.nft
grep -q 'nftables.d/pbn_origin.nft' /etc/nftables.conf 2>/dev/null || \
    echo 'include "/etc/nftables.d/pbn_origin.nft"' >> /etc/nftables.conf
systemctl enable nftables >/dev/null 2>&1

echo "готово: 80 и 443 открыты только для Cloudflare, порт 22 не тронут"
echo "проверка — прямой запрос на origin должен теперь отваливаться:"
echo "   curl -m 5 -H 'Host: drunk-fish.ru' http://157.228.135.19/"
