<?php
/**
 * PBN Manager Proxy Bridge
 * Загрузи этот файл в public_html и вызывай: /pbn-bridge.php?action=...
 *
 * ВАЖНО: Удали после настройки или защити паролем!
 */

// Загружаем WordPress
require_once(dirname(__FILE__) . '/wp-load.php');

// Секретный ключ (поменяй на свой)
$SECRET_KEY = 'pbn_secret_2024';

// Проверка ключа
if (!isset($_GET['key']) || $_GET['key'] !== $SECRET_KEY) {
    http_response_code(403);
    die(json_encode(['error' => 'Invalid key']));
}

header('Content-Type: application/json');

$action = $_GET['action'] ?? '';

switch ($action) {
    case 'info':
        // Информация о сайте
        echo json_encode([
            'status' => 'ok',
            'wp_version' => get_bloginfo('version'),
            'site_url' => get_site_url(),
            'admin_email' => get_option('admin_email'),
            'php_version' => phpversion(),
        ]);
        break;

    case 'create_app_password':
        // Создание Application Password
        require_once(ABSPATH . 'wp-admin/includes/user.php');

        $user = get_user_by('email', $_GET['email'] ?? '');
        if (!$user) {
            $user = get_user_by('login', $_GET['email'] ?? '');
        }

        if (!$user) {
            echo json_encode(['error' => 'User not found']);
            break;
        }

        $app_name = $_GET['app_name'] ?? 'PBN Manager';
        $password = wp_generate_password(24, false);

        $result = WP_Application_Passwords::create_new_application_password(
            $user->ID,
            ['name' => $app_name, 'app_id' => wp_generate_uuid4()]
        );

        if (is_wp_error($result)) {
            echo json_encode(['error' => $result->get_error_message()]);
        } else {
            echo json_encode([
                'status' => 'ok',
                'user_id' => $user->ID,
                'user_login' => $user->user_login,
                'app_password' => $result[0], // Пароль в открытом виде (только при создании)
            ]);
        }
        break;

    case 'test_api':
        // Проверка REST API
        echo json_encode([
            'status' => 'ok',
            'rest_url' => get_rest_url(),
            'api_available' => true,
        ]);
        break;

    default:
        echo json_encode(['error' => 'Unknown action', 'available' => ['info', 'create_app_password', 'test_api']]);
}
