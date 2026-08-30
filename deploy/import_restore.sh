#!/usr/bin/env bash
# Возвращает восстановленные статьи на сайты штатным импортёром WordPress.
#
# Запуск от root на сервере:
#     bash import_restore.sh /var/www/wxr/restore
#     bash import_restore.sh /var/www/wxr/restore drunk-fish.ru
#
# Импортёр WordPress сохраняет исходные post_id, если те свободны — именно так
# вернулись 569 февральских записей. На этом держится восстановление адресов
# вида ?p=ID, поэтому после импорта скрипт сверяет, что ID и слаги совпали с
# заданными, и громко ругается, если нет.
#
# Скрипт ничего не удаляет. Уже импортированные статьи импортёр пропускает сам.

set -uo pipefail

SRC="${1:-/var/www/wxr/restore}"
ONLY="${2:-}"
WEBROOT="${WEBROOT:-/var/www}"
WP_CACHE="${WP_CACHE:-/var/www/.wp-cli-cache}"

say()  { printf '%s\n' "$*"; }
warn() { printf 'ВНИМАНИЕ: %s\n' "$*" >&2; }
fail() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }

wp_run() {
    local path="$1"; shift
    sudo -u www-data -H WP_CLI_CACHE_DIR="$WP_CACHE" wp --path="$path" "$@"
}

[ "$(id -u)" -eq 0 ] || fail "нужны права root"
[ -d "$SRC" ] || fail "нет каталога с файлами: $SRC"

TOTAL_OK=0; TOTAL_BAD=0; FAILED=()

for FILE in "$SRC"/*.wxr.xml; do
    [ -e "$FILE" ] || fail "в $SRC нет файлов *.wxr.xml"
    DOMAIN=$(basename "$FILE" .wxr.xml)
    [ -n "$ONLY" ] && [ "$ONLY" != "$DOMAIN" ] && continue
    ROOT="$WEBROOT/$DOMAIN"

    say ""
    say "--- $DOMAIN"
    if [ ! -f "$ROOT/wp-config.php" ]; then
        warn "$DOMAIN: сайт не развёрнут, пропускаю"
        FAILED+=("$DOMAIN"); continue
    fi

    # Импортёр читает файл от имени www-data — из /root он его не увидит
    chown www-data:www-data "$FILE"

    # Автор берётся тот же, что у уже импортированных записей: новый автор
    # завёл бы вторую страницу архива и разошёлся бы с остальными статьями
    AUTHOR=$(wp_run "$ROOT" db query \
        "SELECT u.user_login FROM wp_posts p JOIN wp_users u ON u.ID=p.post_author \
         WHERE p.post_type='post' LIMIT 1" --skip-column-names 2>/dev/null | head -1)
    if [ -z "$AUTHOR" ]; then
        warn "$DOMAIN: не нашёл автора существующих записей, пропускаю"
        FAILED+=("$DOMAIN"); continue
    fi

    if ! wp_run "$ROOT" import "$FILE" --authors=skip --user="$AUTHOR" --quiet; then
        warn "$DOMAIN: импорт не прошёл"
        FAILED+=("$DOMAIN"); continue
    fi

    # --- сверка: каждая статья из файла обязана стоять на своём ID и слаге
    OK=0; BAD=0
    while IFS='|' read -r PID SLUG; do
        [ -n "$PID" ] || continue
        ACTUAL=$(wp_run "$ROOT" db query \
            "SELECT post_name FROM wp_posts WHERE ID=$PID AND post_type='post' \
             AND post_status='publish'" --skip-column-names 2>/dev/null | head -1)
        if [ "$ACTUAL" = "$SLUG" ]; then
            OK=$((OK+1))
        else
            BAD=$((BAD+1))
            warn "$DOMAIN: ID $PID ждали слаг '$SLUG', в базе '${ACTUAL:-нет записи}'"
        fi
    done < <(python3 - "$FILE" <<'PY'
import sys, re
xml = open(sys.argv[1], encoding='utf-8').read()
for item in re.findall(r'<item>.*?</item>', xml, re.S):
    pid = re.search(r'<wp:post_id>(\d+)</wp:post_id>', item)
    name = re.search(r'<wp:post_name><!\[CDATA\[(.*?)\]\]></wp:post_name>', item)
    if pid and name:
        print(f"{pid.group(1)}|{name.group(1)}")
PY
    )

    say "  сошлось: $OK, разошлось: $BAD"
    TOTAL_OK=$((TOTAL_OK+OK)); TOTAL_BAD=$((TOTAL_BAD+BAD))
    [ "$BAD" -gt 0 ] && FAILED+=("$DOMAIN")
done

say ""
say "=== Итог: статей на своих адресах $TOTAL_OK, с расхождением $TOTAL_BAD ==="
if [ ${#FAILED[@]} -gt 0 ]; then
    warn "проблемные домены (${#FAILED[@]}): ${FAILED[*]}"
    exit 1
fi
