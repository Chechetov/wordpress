#!/usr/bin/env bash
# Куда ушло место на диске. Только чтение, ничего не меняет и не удаляет.
#
# Запускать от root:  bash disk_report.sh

set -uo pipefail

hdr() { printf '\n=== %s ===\n' "$*"; }

hdr "Диск целиком"
df -h / | tail -1

hdr "Крупнейшие каталоги верхнего уровня"
du -shx /* 2>/dev/null | sort -rh | head -12

hdr "Внутри /var (обычно виновник здесь)"
du -shx /var/* 2>/dev/null | sort -rh | head -10

hdr "Логи"
du -sh /var/log 2>/dev/null
find /var/log -type f -size +50M -exec ls -lh {} \; 2>/dev/null | awk '{printf "  %6s  %s\n", $5, $9}' | head -15
say_rotated=$(find /var/log -type f \( -name '*.gz' -o -name '*.1' -o -name '*.old' \) 2>/dev/null | wc -l)
printf '  ротированных файлов: %s (суммарно %s)\n' "$say_rotated" \
    "$(find /var/log -type f \( -name '*.gz' -o -name '*.1' -o -name '*.old' \) -print0 2>/dev/null | du -shc --files0-from=- 2>/dev/null | tail -1 | cut -f1)"

hdr "Базы данных"
du -sh /var/lib/mysql 2>/dev/null || echo "  /var/lib/mysql нет"
echo "  бинарные логи MySQL (их часто можно чистить):"
du -shc /var/lib/mysql/*bin.[0-9]* 2>/dev/null | tail -1 | sed 's/^/    итого: /' || echo "    нет"

hdr "Кеш пакетов"
du -sh /var/cache/apt 2>/dev/null || true
apt-get --just-print autoremove 2>/dev/null | awk '/^Remv/ {n++} END {if (n) printf "  пакетов к удалению: %d\n", n}'

hdr "Сайты"
for d in /var/www /home /srv /usr/share/nginx; do
    [ -d "$d" ] && du -shx "$d" 2>/dev/null
done
echo "  по сайтам:"
for base in /var/www /home; do
    [ -d "$base" ] || continue
    du -shx "$base"/*/ 2>/dev/null | sort -rh | head -25 | sed 's/^/    /'
done

hdr "Медиа WordPress (крупные оригиналы обложек)"
for up in $(find /var/www /home -maxdepth 5 -type d -name uploads 2>/dev/null | head -30); do
    printf '  %8s  %s\n' "$(du -sh "$up" 2>/dev/null | cut -f1)" "$up"
done
echo "  самые тяжёлые файлы в uploads:"
find /var/www /home -path '*/uploads/*' -type f -size +2M 2>/dev/null \
    | head -15 | xargs -r ls -lh 2>/dev/null | awk '{printf "    %6s  %s\n", $5, $9}'

hdr "Удалённые, но удерживаемые процессами файлы"
lsof -nP 2>/dev/null | awk '/deleted/ {sum+=$8} END {if (sum) printf "  %.1f ГБ держат живые процессы (поможет перезапуск сервиса)\n", sum/1024/1024/1024}'

hdr "Память"
free -h
swapon --show 2>/dev/null || echo "  своп не подключён"

printf '\nГотово. Ничего не изменено.\n'
