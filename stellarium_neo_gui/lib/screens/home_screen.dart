import 'package:flutter/material.dart';

import '../services/api_service.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _apiService = ApiService();

  bool _isLoading = false;
  String _statusMessage = '未接続';

  Future<void> _checkBackend() async {
    setState(() {
      _isLoading = true;
      _statusMessage = '接続確認中...';
    });

    try {
      final message = await _apiService.checkStatus();

      if (!mounted) {
        return;
      }

      setState(() {
        _statusMessage = message;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _statusMessage = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Stellarium Neo')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Pythonバックエンド接続確認',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 24),

              Text(_statusMessage, textAlign: TextAlign.center),
              const SizedBox(height: 24),

              ElevatedButton(
                onPressed: _isLoading ? null : _checkBackend,
                child: _isLoading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('接続確認'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
