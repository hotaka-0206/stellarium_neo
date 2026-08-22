import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiService {
  static const String baseUrl = 'http://127.0.0.1:8000';

  Future<String> checkStatus() async {
    final uri = Uri.parse('$baseUrl/api/status');

    try {
      final response = await http.get(uri).timeout(const Duration(seconds: 5));

      if (response.statusCode != 200) {
        throw Exception(
          'Python APIとの通信に失敗しました。'
          ' HTTP ${response.statusCode}',
        );
      }

      final data = jsonDecode(response.body);

      if (data is! Map<String, dynamic>) {
        throw Exception('Python APIから不正な応答が返されました。');
      }

      if (data['success'] != true) {
        throw Exception(
          data['message']?.toString() ?? 'Python APIとの接続確認に失敗しました。',
        );
      }

      return data['message']?.toString() ?? '接続成功';
    } catch (error) {
      throw Exception('Pythonバックエンドに接続できませんでした: $error');
    }
  }
}
