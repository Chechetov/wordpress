<?php
/**
 * PBN Manager Bridge v2
 * Проксирует запросы к WordPress в обход блокировки Hostinger
 */

require_once(dirname(__FILE__) . '/wp-load.php');

$SECRET_KEY = 'pbn_secret_2024';

if (!isset($_GET['key']) || $_GET['key'] !== $SECRET_KEY) {
    http_response_code(403);
    die(json_encode(['error' => 'Invalid key']));
}

header('Content-Type: application/json');
$action = $_GET['action'] ?? '';

switch ($action) {
    case 'info':
        echo json_encode([
            'status' => 'ok',
            'wp_version' => get_bloginfo('version'),
            'site_url' => get_site_url(),
            'admin_email' => get_option('admin_email'),
            'php_version' => phpversion(),
        ]);
        break;

    case 'create_app_password':
        require_once(ABSPATH . 'wp-admin/includes/user.php');
        $user = get_user_by('email', $_GET['email'] ?? '');
        if (!$user) $user = get_user_by('login', $_GET['email'] ?? '');
        if (!$user) { echo json_encode(['error' => 'User not found']); break; }

        $result = WP_Application_Passwords::create_new_application_password(
            $user->ID,
            ['name' => $_GET['app_name'] ?? 'PBN Manager', 'app_id' => wp_generate_uuid4()]
        );

        if (is_wp_error($result)) {
            echo json_encode(['error' => $result->get_error_message()]);
        } else {
            echo json_encode([
                'status' => 'ok',
                'user_login' => $user->user_login,
                'app_password' => $result[0],
            ]);
        }
        break;

    case 'create_post':
        // Получаем данные из POST body
        $input = json_decode(file_get_contents('php://input'), true);
        if (!$input) {
            $input = [
                'title' => $_GET['title'] ?? '',
                'content' => $_GET['content'] ?? '',
                'category' => $_GET['category'] ?? '',
                'status' => $_GET['status'] ?? 'publish',
            ];
        }

        if (empty($input['title']) || empty($input['content'])) {
            echo json_encode(['error' => 'Title and content required']);
            break;
        }

        // Получаем или создаем категорию
        $category_id = 1; // Uncategorized по умолчанию
        if (!empty($input['category'])) {
            $cat = get_category_by_slug(sanitize_title($input['category']));
            if ($cat) {
                $category_id = $cat->term_id;
            } else {
                $new_cat = wp_insert_category(['cat_name' => $input['category']]);
                if (!is_wp_error($new_cat)) {
                    $category_id = $new_cat;
                }
            }
        }

        // Создаем пост
        $post_data = [
            'post_title'    => wp_strip_all_tags($input['title']),
            'post_content'  => $input['content'],
            'post_status'   => $input['status'] ?? 'publish',
            'post_author'   => 1,
            'post_category' => [$category_id],
        ];

        // Отложенная публикация
        if (!empty($input['scheduled_date'])) {
            $post_data['post_status'] = 'future';
            $post_data['post_date'] = $input['scheduled_date'];
            $post_data['post_date_gmt'] = get_gmt_from_date($input['scheduled_date']);
        }

        $post_id = wp_insert_post($post_data);

        if (is_wp_error($post_id)) {
            echo json_encode(['error' => $post_id->get_error_message()]);
        } else {
            echo json_encode([
                'status' => 'ok',
                'post_id' => $post_id,
                'url' => get_permalink($post_id),
                'edit_url' => admin_url("post.php?post={$post_id}&action=edit"),
            ]);
        }
        break;

    case 'upload_image':
        require_once(ABSPATH . 'wp-admin/includes/image.php');
        require_once(ABSPATH . 'wp-admin/includes/file.php');
        require_once(ABSPATH . 'wp-admin/includes/media.php');

        // Загрузка изображения из URL
        $image_url = $_GET['image_url'] ?? '';
        $post_id = intval($_GET['post_id'] ?? 0);

        if (empty($image_url)) {
            echo json_encode(['error' => 'image_url required']);
            break;
        }

        $attachment_id = media_sideload_image($image_url, $post_id, '', 'id');

        if (is_wp_error($attachment_id)) {
            echo json_encode(['error' => $attachment_id->get_error_message()]);
        } else {
            // Устанавливаем как featured image
            if ($post_id > 0) {
                set_post_thumbnail($post_id, $attachment_id);
            }
            echo json_encode([
                'status' => 'ok',
                'attachment_id' => $attachment_id,
                'url' => wp_get_attachment_url($attachment_id),
            ]);
        }
        break;

    case 'get_posts':
        $posts = get_posts([
            'numberposts' => intval($_GET['limit'] ?? 10),
            'post_status' => $_GET['status'] ?? 'any',
        ]);

        $result = [];
        foreach ($posts as $post) {
            $result[] = [
                'id' => $post->ID,
                'title' => $post->post_title,
                'url' => get_permalink($post->ID),
                'status' => $post->post_status,
                'date' => $post->post_date,
            ];
        }
        echo json_encode(['status' => 'ok', 'posts' => $result]);
        break;

    case 'get_categories':
        $categories = get_categories(['hide_empty' => false]);
        $result = [];
        foreach ($categories as $cat) {
            $result[] = ['id' => $cat->term_id, 'name' => $cat->name, 'slug' => $cat->slug];
        }
        echo json_encode(['status' => 'ok', 'categories' => $result]);
        break;

    default:
        echo json_encode([
            'error' => 'Unknown action',
            'available' => ['info', 'create_app_password', 'create_post', 'upload_image', 'get_posts', 'get_categories']
        ]);
}
