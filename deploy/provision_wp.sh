#!/usr/bin/env bash
# Разворачивает WordPress под указанные домены и выдаёт готовый sites.json.
#
# Запуск от root на сервере:
#     bash provision_wp.sh drunk-fish.ru kgdink.ru mai-hoshi.ru
#     DRY_RUN=1 bash provision_wp.sh drunk-fish.ru        # только показать план
#
# Скрипт СТРОГО ДОБАВЛЯЮЩИЙ: существующие сайты, вхосты и базы не трогает.
# Если домен уже развёрнут — пропускает его и идёт дальше. Ничего не удаляет.
#
# В конце печатает JSON с доменами, логинами и паролями приложений —
# скопируйте его целиком и передайте, он нужен для импорта контента.

set -uo pipefail

DRY_RUN="${DRY_RUN:-0}"
WP_USER="${WP_USER:-pbnadmin}"
WEBROOT="${WEBROOT:-/var/www}"
PHP_SOCK=""
OUT_JSON="/root/sites_generated.json"

say()  { printf '%s\n' "$*"; }
warn() { printf 'ВНИМАНИЕ: %s\n' "$*" >&2; }
fail() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = "1" ]; then say "  [показ] $*"; else eval "$@"; fi; }

[ "$(id -u)" -eq 0 ] || fail "нужны права root"
[ $# -gt 0 ] || fail "укажите домены: bash provision_wp.sh domain1.ru domain2.ru"

DOMAINS=("$@")

say "=== Проверка окружения ==="
command -v nginx   >/dev/null && say "  nginx: $(nginx -v 2>&1)" || NEED_NGINX=1
command -v mysql   >/dev/null && say "  БД:    $(mysql --version)" || NEED_DB=1
command -v php     >/dev/null && say "  php:   $(php -v 2>/dev/null | head -1)" || NEED_PHP=1
command -v wp      >/dev/null && say "  wp-cli: есть" || NEED_WPCLI=1

# Ставим только то, чего нет. Существующие сайты это не затрагивает.
if [ "${NEED_NGINX:-0}${NEED_DB:-0}${NEED_PHP:-0}" != "" ]; then
    say ""
    say "=== Доустановка недостающего ==="
    export DEBIAN_FRONTEND=noninteractive
    run "apt-get update -qq"
    [ "${NEED_NGINX:-0}" = "1" ] && run "apt-get install -y -qq nginx"
    [ "${NEED_DB:-0}" = "1" ]    && run "apt-get install -y -qq mariadb-server"
    [ "${NEED_PHP:-0}" = "1" ]   && run "apt-get install -y -qq php-fpm php-mysql php-curl php-gd php-mbstring php-xml php-zip"
fi

if [ "${NEED_WPCLI:-0}" = "1" ]; then
    say "  ставлю wp-cli"
    run "curl -sS -o /usr/local/bin/wp https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar"
    run "chmod +x /usr/local/bin/wp"
fi

# Сокет PHP-FPM — версия может быть любой
PHP_SOCK=$(ls /run/php/php*-fpm.sock 2>/dev/null | head -1)
[ -n "$PHP_SOCK" ] || { [ "$DRY_RUN" = "1" ] && PHP_SOCK=/run/php/phpX-fpm.sock || fail "не нашёл сокет php-fpm"; }
say "  сокет php-fpm: $PHP_SOCK"

# Один общий пул PHP-FPM экономнее, чем пул на сайт: на 1 ГБ это критично
POOL=$(ls /etc/php/*/fpm/pool.d/www.conf 2>/dev/null | head -1)
if [ -n "$POOL" ] && [ "$DRY_RUN" != "1" ]; then
    if ! grep -q '^pm = ondemand' "$POOL"; then
        cp "$POOL" "$POOL.bak.$(date +%s)"
        sed -i 's/^pm = .*/pm = ondemand/' "$POOL"
        sed -i 's/^pm.max_children = .*/pm.max_children = 6/' "$POOL"
        grep -q '^pm.process_idle_timeout' "$POOL" || echo 'pm.process_idle_timeout = 10s' >> "$POOL"
        say "  PHP-FPM переведён в ondemand, max_children=6 (бэкап рядом)"
    fi
fi

rand() { tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-20}"; }

# wp-cli пишет кеш в $HOME, а домашний каталог www-data ему недоступен —
# без своего каталога он сыплет предупреждениями на каждую команду
WP_CACHE="${WP_CACHE:-/var/www/.wp-cli-cache}"
if [ "$DRY_RUN" != "1" ]; then
    mkdir -p "$WP_CACHE"
    chown www-data:www-data "$WP_CACHE"
fi

say ""
say "=== Развёртывание ==="
RESULTS=()
FAILED=()
for DOMAIN in "${DOMAINS[@]}"; do
    ROOT="$WEBROOT/$DOMAIN"
    SAFE=$(echo "$DOMAIN" | tr '.-' '__' | cut -c1-24)
    DB="wp_$SAFE"
    DBUSER="u_$(echo "$SAFE" | cut -c1-12)"

    say ""
    say "--- $DOMAIN"
    if [ -f "$ROOT/wp-config.php" ]; then
        say "  уже развёрнут, пропускаю"
        continue
    fi

    DBPASS=$(rand 24)
    ADMPASS=$(rand 20)

    # Каталог сразу отдаём www-data: wp-cli работает от него и в чужой
    # каталог писать не может. Раньше chown стоял в конце, и все команды
    # wp падали на «is not writable by current user», а скрипт всё равно
    # рапортовал «готово».
    run "mkdir -p '$ROOT'"
    run "chown www-data:www-data '$ROOT'"
    run "mysql -e \"CREATE DATABASE IF NOT EXISTS \\\`$DB\\\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\""
    run "mysql -e \"CREATE USER IF NOT EXISTS '$DBUSER'@'localhost' IDENTIFIED BY '$DBPASS';\""
    # Пароль задаём отдельно: при повторном запуске CREATE USER IF NOT EXISTS
    # молча оставит старый, и свежий wp-config.php не подойдёт к базе.
    run "mysql -e \"ALTER USER '$DBUSER'@'localhost' IDENTIFIED BY '$DBPASS';\""
    run "mysql -e \"GRANT ALL PRIVILEGES ON \\\`$DB\\\`.* TO '$DBUSER'@'localhost'; FLUSH PRIVILEGES;\""

    if ! run "sudo -u www-data -H WP_CLI_CACHE_DIR='$WP_CACHE' wp core download --path='$ROOT' --locale=ru_RU --quiet"; then
        warn "$DOMAIN: не удалось скачать WordPress — пропускаю домен"
        FAILED+=("$DOMAIN")
        continue
    fi
    run "sudo -u www-data -H WP_CLI_CACHE_DIR='$WP_CACHE' wp config create --path='$ROOT' --dbname='$DB' --dbuser='$DBUSER' --dbpass='$DBPASS' --locale=ru_RU --quiet"
    run "sudo -u www-data -H WP_CLI_CACHE_DIR='$WP_CACHE' wp core install --path='$ROOT' --url='https://$DOMAIN' --title='$DOMAIN' --admin_user='$WP_USER' --admin_password='$ADMPASS' --admin_email='admin@$DOMAIN' --skip-email --quiet"
    # Пермалинки обязаны совпадать со старыми, иначе перелинковка из выгрузки развалится
    run "sudo -u www-data -H WP_CLI_CACHE_DIR='$WP_CACHE' wp rewrite structure '/%category%/%postname%/' --path='$ROOT' --quiet"
    run "sudo -u www-data -H WP_CLI_CACHE_DIR='$WP_CACHE' wp option update blog_public 1 --path='$ROOT' --quiet"

    cat > "/etc/nginx/sites-available/$DOMAIN" <<NGINX
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    root $ROOT;
    index index.php index.html;

    location / { try_files \$uri \$uri/ /index.php?\$args; }
    location ~ \.php\$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:$PHP_SOCK;
    }
    location ~* \.(jpg|jpeg|png|gif|webp|css|js|ico|svg)\$ {
        expires 30d;
        access_log off;
    }
    location ~ /\.ht { deny all; }
}
NGINX
    run "ln -sf '/etc/nginx/sites-available/$DOMAIN' '/etc/nginx/sites-enabled/$DOMAIN'"
    run "chown -R www-data:www-data '$ROOT'"

    if [ "$DRY_RUN" != "1" ]; then
        APPPASS=$(sudo -u www-data -H WP_CLI_CACHE_DIR="$WP_CACHE" wp user application-password create \
                      "$WP_USER" "recovery" --porcelain --path="$ROOT" 2>&1 | tail -1)
        # Пустой пароль означает, что сайт на самом деле не поднялся:
        # молча записывать такую строку в sites.json нельзя, дальше по ней
        # пойдёт импорт и упрётся в 401.
        if [ -z "$APPPASS" ] || echo "$APPPASS" | grep -qi 'error'; then
            warn "$DOMAIN: пароль приложения не создан ($APPPASS)"
            FAILED+=("$DOMAIN")
            continue
        fi
        RESULTS+=("{\"domain\":\"$DOMAIN\",\"url\":\"https://$DOMAIN\",\"username\":\"$WP_USER\",\"password\":\"$APPPASS\"}")
        say "  готово: база $DB, вхост создан, пароль приложения получен"
    else
        say "  [показ] будет создан сайт, база $DB и пароль приложения"
    fi
done

if [ "$DRY_RUN" != "1" ]; then
    say ""
    say "=== Перезапуск ==="
    if nginx -t 2>/dev/null; then
        systemctl reload nginx && say "  nginx перечитал конфиг"
    else
        warn "nginx -t не прошёл, конфиг НЕ перечитан — проверьте вручную"
    fi

    if [ ${#RESULTS[@]} -gt 0 ]; then
        printf '[\n' > "$OUT_JSON"
        for i in "${!RESULTS[@]}"; do
            sep=","; [ "$i" -eq $(( ${#RESULTS[@]} - 1 )) ] && sep=""
            printf ' %s%s\n' "${RESULTS[$i]}" "$sep" >> "$OUT_JSON"
        done
        printf ']\n' >> "$OUT_JSON"
        chmod 600 "$OUT_JSON"
        say ""
        say "=== СКОПИРУЙТЕ ЭТО ЦЕЛИКОМ ==="
        cat "$OUT_JSON"
        say "=== КОНЕЦ (копия сохранена в $OUT_JSON) ==="
    fi
fi

if [ ${#FAILED[@]} -gt 0 ]; then
    say ""
    warn "не развернулись (${#FAILED[@]}): ${FAILED[*]}"
fi

say ""
say "Готово. Сайты отвечают только по HTTP — сертификаты не нужны:"
say "Cloudflare в режиме Full сам терминирует TLS, а до origin ходит по HTTP."
