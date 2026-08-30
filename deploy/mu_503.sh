#!/usr/bin/env bash
# Ставит (или снимает) временную заглушку: пока сайты дозаполняются,
# несуществующий адрес отдаёт 503 с Retry-After, а не 404.
#
#     bash mu_503.sh install 2026-09-07
#     bash mu_503.sh remove
#
# Зачем: 404 говорит поисковику «страницы больше нет» и выбивает адрес из
# индекса. 503 с Retry-After — «временно, зайдите позже», и адрес сохраняется.
# Пока часть статей ещё не вернулась на место, это разница между «переезд
# прошёл незаметно» и «потеряли адреса, которые сами же и восстанавливали».
#
# Заглушка самоотключается: после указанной даты она перестаёт вмешиваться,
# даже если её забыли снять. Долго держать 503 нельзя — поисковик в конце
# концов решит, что сайт умер.

set -uo pipefail

MODE="${1:-}"
UNTIL="${2:-2026-09-07}"
WEBROOT="${WEBROOT:-/var/www}"
NAME="pbn-temporary-503.php"

[ "$(id -u)" -eq 0 ] || { echo "нужны права root" >&2; exit 1; }
case "$MODE" in
    install|remove) ;;
    *) echo "использование: bash mu_503.sh install [ДАТА] | remove" >&2; exit 1 ;;
esac

COUNT=0
for ROOT in "$WEBROOT"/*/; do
    [ -f "$ROOT/wp-config.php" ] || continue
    MUDIR="$ROOT/wp-content/mu-plugins"
    TARGET="$MUDIR/$NAME"

    if [ "$MODE" = "remove" ]; then
        [ -f "$TARGET" ] && rm -f "$TARGET" && COUNT=$((COUNT+1))
        continue
    fi

    mkdir -p "$MUDIR"
    cat > "$TARGET" <<PHP
<?php
/**
 * Plugin Name: Временный 503 вместо 404
 * Description: На время восстановления сайта несуществующий адрес отдаёт 503
 *              с Retry-After, чтобы поисковик не выбросил его из индекса.
 *              Самоотключается после ACTIVE_UNTIL.
 */
define('PBN_503_ACTIVE_UNTIL', '$UNTIL');

add_action('template_redirect', function () {
    if (!is_404()) {
        return;
    }
    if (current_time('Y-m-d') > PBN_503_ACTIVE_UNTIL) {
        return; // срок вышел — снова обычный 404
    }
    status_header(503);
    header('Retry-After: 86400');
    nocache_headers();
});
PHP
    chown www-data:www-data "$TARGET"
    COUNT=$((COUNT+1))
done

if [ "$MODE" = "install" ]; then
    echo "заглушка поставлена на $COUNT сайтов, действует по $UNTIL включительно"
else
    echo "заглушка снята с $COUNT сайтов"
fi
