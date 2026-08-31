import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  const ApiException({
    required this.code,
    required this.message,
    this.details = const <String, dynamic>{},
  });

  final String code;
  final String message;
  final Map<String, dynamic> details;

  @override
  String toString() => message;
}

class TargetInfo {
  const TargetInfo({
    required this.fullName,
    required this.shortName,
    required this.primaryDesignation,
    required this.spkId,
    required this.horizonsCommand,
    required this.defaultDisplayName,
    required this.isRegistered,
    this.minorPlanetNumber,
    this.iauDesignation,
  });

  final String fullName;
  final String shortName;
  final String primaryDesignation;
  final String spkId;
  final String horizonsCommand;
  final String defaultDisplayName;
  final bool isRegistered;
  final String? minorPlanetNumber;
  final String? iauDesignation;

  factory TargetInfo.fromApiData(Map<String, dynamic> data) {
    final identity = data['identity'];
    if (identity is! Map<String, dynamic>) {
      throw const FormatException('天体情報の形式が不正です。');
    }

    return TargetInfo(
      fullName: identity['full_name']?.toString() ?? '',
      shortName: identity['short_name']?.toString() ?? '',
      primaryDesignation:
          identity['primary_designation']?.toString() ?? '',
      spkId: identity['spk_id']?.toString() ?? '',
      horizonsCommand: identity['horizons_command']?.toString() ?? '',
      defaultDisplayName:
          identity['default_display_name']?.toString() ?? '',
      minorPlanetNumber: identity['minor_planet_number']?.toString(),
      iauDesignation: identity['iau_designation']?.toString(),
      isRegistered: data['existing_object'] != null,
    );
  }
}

class ApiService {
  static const String baseUrl = 'http://127.0.0.1:8000';

  Future<String> checkStatus() async {
    final data = await _requestJson(
      method: 'GET',
      path: '/api/status',
    );
    return data['message']?.toString() ?? '接続成功';
  }

  Future<TargetInfo> inspectTarget(String identifier) async {
    final data = await _requestJson(
      method: 'POST',
      path: '/api/target/inspect',
      body: {'identifier': identifier},
    );

    final targetData = data['data'];
    if (targetData is! Map<String, dynamic>) {
      throw const ApiException(
        code: 'invalid_backend_response',
        message: 'Python APIから天体情報を取得できませんでした。',
      );
    }

    return TargetInfo.fromApiData(targetData);
  }

  Future<Map<String, dynamic>> _requestJson({
    required String method,
    required String path,
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');

    late http.Response response;
    try {
      switch (method) {
        case 'GET':
          response = await http.get(uri).timeout(const Duration(seconds: 8));
          break;
        case 'POST':
          response = await http
              .post(
                uri,
                headers: const {'Content-Type': 'application/json'},
                body: jsonEncode(body ?? const <String, dynamic>{}),
              )
              .timeout(const Duration(seconds: 30));
          break;
        default:
          throw UnsupportedError('未対応のHTTPメソッドです: $method');
      }
    } on TimeoutException {
      throw const ApiException(
        code: 'backend_timeout',
        message: 'Pythonバックエンドから応答がありません。',
      );
    } on http.ClientException {
      throw const ApiException(
        code: 'backend_connection_failed',
        message: 'Pythonバックエンドに接続できませんでした。',
      );
    }

    dynamic decoded;
    try {
      decoded = jsonDecode(response.body);
    } catch (_) {
      throw ApiException(
        code: 'invalid_backend_response',
        message:
            'Python APIからJSON以外の応答が返されました。 HTTP ${response.statusCode}',
      );
    }

    if (decoded is! Map<String, dynamic>) {
      throw const ApiException(
        code: 'invalid_backend_response',
        message: 'Python APIから不正な応答が返されました。',
      );
    }

    if (response.statusCode < 200 ||
        response.statusCode >= 300 ||
        decoded['success'] != true) {
      throw _extractApiException(decoded, response.statusCode);
    }

    return decoded;
  }

  ApiException _extractApiException(
    Map<String, dynamic> data,
    int statusCode,
  ) {
    final error = data['error'];
    if (error is Map<String, dynamic>) {
      final code = error['code']?.toString() ?? 'http_$statusCode';
      final message =
          error['message']?.toString() ??
          error['detail']?.toString() ??
          code;
      final details = error['details'];

      return ApiException(
        code: code,
        message: message,
        details: details is Map<String, dynamic>
            ? details
            : const <String, dynamic>{},
      );
    }

    final message =
        data['message']?.toString() ??
        data['detail']?.toString() ??
        'HTTP $statusCode';

    return ApiException(
      code: 'http_$statusCode',
      message: message,
    );
  }
}
