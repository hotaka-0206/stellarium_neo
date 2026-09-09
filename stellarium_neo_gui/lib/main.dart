import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import 'screens/home_screen.dart';
import 'services/backend_service.dart';

final BackendService _backendService = BackendService();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await windowManager.ensureInitialized();
  await windowManager.setPreventClose(true);

  await _backendService.ensureRunning();

  runApp(
    StellariumNeoApp(
      backendService: _backendService,
    ),
  );
}

class StellariumNeoApp extends StatefulWidget {
  const StellariumNeoApp({
    super.key,
    required this.backendService,
  });

  final BackendService backendService;

  @override
  State<StellariumNeoApp> createState() => _StellariumNeoAppState();
}

class _StellariumNeoAppState extends State<StellariumNeoApp>
    with WindowListener {
  bool _closing = false;

  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);
  }

  @override
  void onWindowClose() async {
    if (_closing) {
      return;
    }

    final isPreventClose = await windowManager.isPreventClose();
    if (!isPreventClose) {
      return;
    }

    _closing = true;

    // Flutter自身が起動したバックエンドだけ停止する。
    await widget.backendService.stop();

    // バックエンド停止後にFlutterウィンドウを終了する。
    await windowManager.destroy();
  }

  @override
  void dispose() {
    windowManager.removeListener(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Stellarium Neo',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
