#!/usr/bin/env bash
# Перенос origin сети на новый сервер.
#
# Зачем: origin в России за Cloudflare не работает — всё, что крупнее 24 КБ,
# не доходит от сервера до Cloudflare (проверено 02.09.2026, см. хенд-офф).
# Cloudflare при этом остаётся: аккаунты, пары NS и Search Protection не
# трогаются, меняется только A-запись через cf_repoint.py.
#
# Скрипт ничего не удаляет на старом сервере: он только читает. Пока не
# переключены A-записи, старый origin продолжает обслуживать сеть, так что
# откат — это просто не переключать записи.
#
#   bash deploy/migrate_origin.sh --target 1.2.3.4 --key ~/.ssh/hostinger --dry-run
#   bash deploy/migrate_origin.sh --target 1.2.3.4 --key ~/.ssh/hostinger
#   bash deploy/migrate_origin.sh --target 1.2.3.4 --key ~/.ssh/hostinger --only yellodigital.ru
set -euo pipefail

SRC=${SRC:-root@157.228.135.19}
SRC_KEY=${SRC_KEY:-$HOME/.ssh/pbn_recovery}
TARGET=""
KEY=""
ONLY=""
DRY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --target) TARGET="$2"; shift 2 ;;
        --key)    KEY="$2"; shift 2 ;;
        --only)   ONLY="$2"; shift 2 ;;
        --dry-run) DRY=1; shift ;;
        *) echo "неизвестный параметр: $1"; exit 2 ;;
    esac
done
[ -n "$TARGET" ] || { echo "нужен --target IP нового сервера"; exit 2; }
[ -n "$KEY" ] || { echo "нужен --key путь к ssh-ключу нового сервера"; exit 2; }
KEY="${KEY/#\~/$HOME}"
[ -f "$KEY" ] || { echo "ключа нет: $KEY"; exit 2; }

DST="root@${TARGET}"
s() { ssh -i "$SRC_KEY" -o BatchMode=yes -o ConnectTimeout=20 "$SRC" "$@"; }
d() { ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new "$DST" "$@"; }
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

say "Проверка доступа"
echo "  старый: $(s 'hostname; . /etc/os-release; echo "  $PRETTY_NAME"')"
echo "  новый:  $(d 'hostname; . /etc/os-release; echo "  $PRETTY_NAME"; nproc | sed "s/^/  ядер: /"; free -m | awk "NR==2{print \"  память: \"\$2\" МБ\"}"')"

SITES=$(s "ls -1 /var/www | while read x; do [ -f /var/www/\$x/wp-config.php ] && echo \$x; done")
[ -n "$ONLY" ] && SITES=$(echo "$SITES" | grep -Fx -- "$(echo "$ONLY" | tr ',' '\n')" || true)
[ -n "$SITES" ] || { echo "под фильтр ничего не попало"; exit 1; }
COUNT=$(echo "$SITES" | wc -l | tr -d ' ')
say "К переносу сайтов: $COUNT"
echo "$SITES" | sed 's/^/  /'

if [ "$DRY" = 1 ]; then
    say "РЕЖИМ ПРОСМОТРА — ничего не делаем"
    echo "  объём: $(s 'du -sh /var/www | cut -f1')"
    echo "  баз:   $(s "mysql -N -B -e \"SELECT COUNT(DISTINCT table_schema) FROM information_schema.tables WHERE table_schema LIKE 'wp\\_%'\"")"
    exit 0
fi

say "1/6 Ставлю на новом сервере тот же стек"
d 'export DEBIAN_FRONTEND=noninteractive
   apt-get update -qq
   apt-get install -y -qq nginx mariadb-server php8.2-fpm php8.2-mysql php8.2-xml \
       php8.2-curl php8.2-gd php8.2-mbstring php8.2-zip php8.2-intl rsync curl less >/dev/null
   command -v wp >/dev/null || { curl -sS -o /usr/local/bin/wp \
       https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar
       chmod +x /usr/local/bin/wp; }
   systemctl enable --now nginx mariadb php8.2-fpm >/dev/null 2>&1
   echo "  стек готов: nginx $(nginx -v 2>&1 | grep -oE "[0-9.]+"), php $(php -v | head -1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+")"'

say "2/6 Своп, если памяти мало"
d 'if ! swapon --show | grep -q .; then
     fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
     grep -q "^/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
     echo "  своп 2 ГБ поднят"
   else echo "  своп уже есть"; fi'

say "3/6 Переношу файлы сайтов"
for site in $SITES; do
    printf '  %-28s ' "$site"
    s "cd /var/www && tar czf - '$site'" \
      | d "mkdir -p /var/www && tar xzf - -C /var/www && chown -R www-data:www-data '/var/www/$site'"
    echo "перенесён ($(d "du -sh /var/www/$site | cut -f1"))"
done

say "4/6 Переношу базы"
for site in $SITES; do
    DB=$(s "grep -oP \"DB_NAME'\s*,\s*'\K[^']+\" '/var/www/$site/wp-config.php'")
    USER=$(s "grep -oP \"DB_USER'\s*,\s*'\K[^']+\" '/var/www/$site/wp-config.php'")
    PASS=$(s "grep -oP \"DB_PASSWORD'\s*,\s*'\K[^']+\" '/var/www/$site/wp-config.php'")
    printf '  %-28s ' "$site"
    d "mysql -e \"CREATE DATABASE IF NOT EXISTS \\\`$DB\\\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
                 CREATE USER IF NOT EXISTS '$USER'@'localhost' IDENTIFIED BY '$PASS';
                 GRANT ALL ON \\\`$DB\\\`.* TO '$USER'@'localhost'; FLUSH PRIVILEGES;\""
    s "mysqldump --single-transaction --quick --default-character-set=utf8mb4 '$DB'" \
      | d "mysql --default-character-set=utf8mb4 '$DB'"
    echo "база $DB перенесена ($(d "mysql -N -B -e \"SELECT COUNT(*) FROM \\\`$DB\\\`.wp_posts WHERE post_type='post' AND post_status='publish'\"") записей)"
done

say "5/6 Переношу конфигурацию nginx и сертификат origin"
s 'tar czf - -C /etc/nginx sites-available ssl' | d 'tar xzf - -C /etc/nginx'
d 'mkdir -p /etc/nginx/sites-enabled
   for f in /etc/nginx/sites-available/*; do
     [ "$(basename "$f")" = "default" ] && continue
     ln -sf "$f" "/etc/nginx/sites-enabled/$(basename "$f")"
   done
   rm -f /etc/nginx/sites-enabled/default
   nginx -t 2>&1 | tail -2 | sed "s/^/  /"
   systemctl reload nginx'

say "6/6 Переношу служебные скрипты"
s 'tar czf - -C /root $(cd /root && ls *.sh 2>/dev/null | tr "\n" " ")' | d 'tar xzf - -C /root' || true
d 'ls /root/*.sh 2>/dev/null | xargs -n1 basename | tr "\n" " " | sed "s/^/  /"; echo'

say "Проверка на новом сервере (мимо Cloudflare, по локальному адресу)"
printf '  %-28s %-6s %-10s %s\n' САЙТ КОД РАЗМЕР СЕКУНД
for site in $SITES; do
    r=$(d "curl -sSk --resolve '$site:443:127.0.0.1' -o /dev/null \
           -w '%{http_code} %{size_download} %{time_total}' 'https://$site/'" 2>/dev/null || echo "ERR 0 0")
    # shellcheck disable=SC2086
    set -- $r
    printf '  %-28s %-6s %-10s %s\n' "$site" "$1" "$2" "$3"
done

cat <<'NEXT'

Дальше — вручную, по одному домену, чтобы было чем откатиться:

  1. python3 cf_repoint.py --ip НОВЫЙ_IP --only ДОМЕН --dry-run
  2. python3 cf_repoint.py --ip НОВЫЙ_IP --only ДОМЕН
  3. проверить, что крупные файлы теперь доходят целиком:
       curl -4 -sS -o /dev/null -w '%{size_download} %{time_total}\n' https://ДОМЕН/
  4. python3 cf_allowlist_swap.py --old 157.228.135.19 --new НОВЫЙ_IP --only ДОМЕН
  5. когда переедут все — bash /root/lock_origin.sh install на новом сервере

Старый сервер не трогаем, пока сеть не проверена: откат — вернуть A-запись.
NEXT
