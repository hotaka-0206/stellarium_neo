import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

class BackendStartResult {
  const BackendStartResult({
    required this.success,
    required this.startedByApp,
    required this.message,
  });

  final bool success;
  final bool startedByApp;
  final String message;
}

class BackendService {
  static final Uri _statusUri =
      Uri.parse('http://127.0.0.1:8000/api/status');

  Process? _process;

  bool get startedByApp => _process != null;

  Future<BackendStartResult> ensureRunning() async {
    if (await _isHealthy()) {
      return const BackendStartResult(
        success: true,
        startedByApp: false,
        message: 'Pythonバックエンドは既に起動しています。',
      );
    }

    if (!Platform.isWindows) {
      return const BackendStartResult(
        success: false,
        startedByApp: false,
        message: 'バックエンドの自動起動は現在Windows版のみ対応しています。',
      );
    }

    final backendExecutable = _findBackendExecutable();

    if (!await backendExecutable.exists()) {
      return BackendStartResult(
        success: false,
        startedByApp: false,
        message: 'バックエンド実行ファイルが見つかりません: '
            '${backendExecutable.path}',
      );
    }

    try {
      _process = await Process.start(
        backendExecutable.path,
        const [],
        workingDirectory: backendExecutable.parent.path,
        mode: ProcessStartMode.normal,
      );

      // 子プロセスの出力バッファが詰まって停止しないように読み捨てる。
      unawaited(_process!.stdout.drain<void>());
      unawaited(_process!.stderr.drain<void>());
    } on ProcessException catch (error) {
      _process = null;
      return BackendStartResult(
        success: false,
        startedByApp: false,
        message: 'Pythonバックエンドを起動できませんでした: ${error.message}',
      );
    }

    // Uvicornの起動完了を待つ。
    for (var i = 0; i < 30; i++) {
      if (await _isHealthy()) {
        return const BackendStartResult(
          success: true,
          startedByApp: true,
          message: 'Pythonバックエンドを自動起動しました。',
        );
      }

      await Future<void>.delayed(const Duration(milliseconds: 200));
    }

    await stop();

    return const BackendStartResult(
      success: false,
      startedByApp: false,
      message: 'Pythonバックエンドを起動しましたが、APIの応答を確認できませんでした。',
    );
  }

  Future<void> stop() async {
    final process = _process;
    _process = null;

    if (process == null) {
      return;
    }

    process.kill();
  }

  File _findBackendExecutable() {
    final appDirectory = File(Platform.resolvedExecutable).parent;

    return File(
      '${appDirectory.path}'
      '${Platform.pathSeparator}backend'
      '${Platform.pathSeparator}stellarium_neo_backend.exe',
    );
  }

  Future<bool> _isHealthy() async {
    try {
      final response = await http
          .get(_statusUri)
          .timeout(const Duration(milliseconds: 500));

      if (response.statusCode != HttpStatus.ok) {
        return false;
      }

      final decoded = jsonDecode(response.body);

      return decoded is Map<String, dynamic> &&
          decoded['success'] == true;
    } catch (_) {
      return false;
    }
  }
}
