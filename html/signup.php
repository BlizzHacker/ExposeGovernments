<?php
header('Content-Type: application/json');

// Get JSON input
$input = json_decode(file_get_contents('php://input'), true);

if (!$input || !isset($input['email'])) {
    http_response_code(400);
    echo json_encode(['success' => false, 'message' => 'Email is required']);
    exit;
}

$email = filter_var($input['email'], FILTER_SANITIZE_EMAIL);
if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'message' => 'Invalid email address']);
    exit;
}

// Store email in file (simple database)
$dataFile = __DIR__ . '/subscribers.json';
$subscribers = [];

if (file_exists($dataFile)) {
    $subscribers = json_decode(file_get_contents($dataFile), true) ?: [];
}

// Check if already subscribed
foreach ($subscribers as $sub) {
    if (strtolower($sub['email']) === strtolower($email)) {
        echo json_encode(['success' => true, 'message' => 'You are already subscribed!']);
        exit;
    }
}

// Add new subscriber
$subscribers[] = [
    'email' => $email,
    'subscribed_at' => date('Y-m-d H:i:s'),
    'name' => isset($input['name']) ? $input['name'] : ''
];

file_put_contents($dataFile, json_encode($subscribers, JSON_PRETTY_PRINT));

// Send welcome email
$to = $email;
$subject = "Welcome to ExposeMiamiOK! 🎉";

$welcomeEmail = file_get_contents(__DIR__ . '/welcome-email.html');
$welcomeEmail = str_replace('{{EMAIL}}', htmlspecialchars($email), $welcomeEmail);
$welcomeEmail = str_replace('{{DATE}}', date('F j, Y'), $welcomeEmail);

$headers = [
    'From: ExposeMiamiOK <expose@moveweight.net>',
    'Reply-To: expose@moveweight.net',
    'MIME-Version: 1.0',
    'Content-Type: text/html; charset=UTF-8',
    'X-Mailer: PHP/' . phpversion()
];

mail($to, $subject, $welcomeEmail, implode("\r\n", $headers), '-f expose@moveweight.net');

echo json_encode([
    'success' => true, 
    'message' => 'Welcome! Check your email for next steps.'
]);
