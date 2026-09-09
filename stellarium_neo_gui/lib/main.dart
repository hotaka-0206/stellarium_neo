import 'dart:async';

import 'package:flutter/material.dart';

import 'screens/home_screen.dart';
import 'services/backend_service.dart';

final BackendService _backendService = BackendService();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 既にバックエンドが動いていればそのまま利用し、
  // 動いていなければ配布フォルダ内のexeを自動起動する。
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
    with WidgetsBindingObserver {
  bool _backendStopped = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) {
      unawaited(_stopBackend());
    }
  }

  Future<void> _stopBackend() async {
    if (_backendStopped) {
      return;
    }

    _backendStopped = true;
    await widget.backendService.stop();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_stopBackend());
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
