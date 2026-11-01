import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

class ObserverMapSelection {
  const ObserverMapSelection({
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.altitude,
  });

  final String name;
  final double latitude;
  final double longitude;
  final double altitude;
}

/// 地図表示と現在地取得のみ担当する。JPLやStellarium APIには触れない。
class ObserverMapPicker extends StatefulWidget {
  const ObserverMapPicker({
    super.key,
    required this.initialLatitude,
    required this.initialLongitude,
  });

  final double initialLatitude;
  final double initialLongitude;

  @override
  State<ObserverMapPicker> createState() => _ObserverMapPickerState();
}

class _ObserverMapPickerState extends State<ObserverMapPicker> {
  final MapController _mapController = MapController();
  late LatLng _selected;
  bool _mapReady = false;
  bool _busy = false;
  String? _error;
  double? _locationAccuracy;
  bool _fromCurrentLocation = false;
  bool _confirming = false;
  bool _hasEstimatedElevation = false;
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _altitudeController = TextEditingController();
  final GlobalKey<FormState> _confirmFormKey = GlobalKey<FormState>();

  @override
  void initState() {
    super.initState();
    _selected = LatLng(widget.initialLatitude, widget.initialLongitude);
  }

  @override
  void dispose() {
    _mapController.dispose();
    _nameController.dispose();
    _altitudeController.dispose();
    super.dispose();
  }

  void _setPoint(LatLng point) {
    setState(() {
      _selected = point;
      _fromCurrentLocation = false;
      _locationAccuracy = null;
      _error = null;
    });
  }

  Future<void> _useCurrentLocation() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw StateError('Windowsの位置情報サービスがオフです。設定から有効にしてください。');
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        throw StateError('位置情報の利用が許可されていません。Windowsの設定を確認してください。');
      }

      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 20),
        ),
      );
      if (!mounted) return;
      final point = LatLng(position.latitude, position.longitude);
      setState(() {
        _selected = point;
        _fromCurrentLocation = true;
        _locationAccuracy = position.accuracy;
      });
      if (_mapReady) {
        _mapController.move(point, 15);
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = '現在地を取得できませんでした: $error');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// 公開標高APIは1回/秒の制限があるため、地図移動中には呼ばず確定時のみ照会する。
  Future<double?> _getEstimatedElevation(LatLng location) async {
    final uri = Uri.https(
      'api.opentopodata.org',
      '/v1/mapzen',
      {
        'locations':
            '${location.latitude.toStringAsFixed(6)},'
            '${location.longitude.toStringAsFixed(6)}',
      },
    );
    try {
      final response = await http.get(uri).timeout(const Duration(seconds: 12));
      if (response.statusCode != 200) return null;
      final payload = jsonDecode(response.body);
      if (payload is! Map || payload['status'] != 'OK') return null;
      final entries = payload['results'];
      if (entries is! List || entries.isEmpty) return null;
      final value = entries.first['elevation'];
      if (value is num && value.toDouble().isFinite) {
        return value.toDouble();
      }
    } catch (_) {
      // 標高を取得できないときは、利用者の手入力に切り替える。
    }
    return null;
  }

  // Confirm within the same dialog route; no nested Navigator.pop calls.
  Future<void> _confirmPoint() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });

    final point = _selected;
    final estimatedElevation = await _getEstimatedElevation(point);
    if (!mounted) return;

    _nameController.text = _fromCurrentLocation ? '現在地' : '地図で指定した地点';
    _altitudeController.text = estimatedElevation?.toStringAsFixed(1) ?? '';
    setState(() {
      _busy = false;
      _hasEstimatedElevation = estimatedElevation != null;
      _confirming = true;
    });
  }

  void _applySelectedPoint() {
    if (!(_confirmFormKey.currentState?.validate() ?? false)) return;
    Navigator.of(context).pop(
      ObserverMapSelection(
        name: _nameController.text.trim().isEmpty
            ? '地図で指定した地点'
            : _nameController.text.trim(),
        latitude: _selected.latitude,
        longitude: _selected.longitude,
        altitude: double.parse(_altitudeController.text.trim()),
      ),
    );
  }

  Widget _buildConfirmScreen() {
    return AlertDialog(
      scrollable: true,
      title: const Text('観測地点を確認'),
      content: SizedBox(
        width: 420,
        child: Form(
          key: _confirmFormKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('緯度: ${_selected.latitude.toStringAsFixed(6)}°'),
              Text('経度: ${_selected.longitude.toStringAsFixed(6)}°'),
              const SizedBox(height: 12),
              TextFormField(
                controller: _nameController,
                decoration: const InputDecoration(labelText: '地点名'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _altitudeController,
                keyboardType: const TextInputType.numberWithOptions(
                  signed: true,
                  decimal: true,
                ),
                decoration: InputDecoration(
                  labelText: '標高 [m]（修正可能）',
                  helperText: _hasEstimatedElevation
                      ? '地形データによる推定標高です。'
                      : '自動取得できませんでした。標高を入力してください。',
                ),
                validator: (value) {
                  final number = double.tryParse(value?.trim() ?? '');
                  return number == null || !number.isFinite
                      ? '標高を数値で入力してください。'
                      : null;
                },
              ),
              const SizedBox(height: 12),
              const Text(
                '注意: 地形の標高は概算です。JPL Horizonsが要求する'
                '楕円体高と一致しない場合があります。精密な観測地点には補正してください。',
                style: TextStyle(fontSize: 12),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => setState(() => _confirming = false),
          child: const Text('地図に戻る'),
        ),
        FilledButton(
          onPressed: _applySelectedPoint,
          child: const Text('観測地点に反映'),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_confirming) return _buildConfirmScreen();
    final size = MediaQuery.sizeOf(context);
    final width = math.max(300.0, math.min(850.0, size.width - 80));
    final height = math.max(220.0, math.min(420.0, size.height - 360));
    return AlertDialog(
      scrollable: true,
      title: const Text('地図から観測地点を選択'),
      content: SizedBox(
        width: width,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                FilledButton.tonalIcon(
                  onPressed: _busy ? null : _useCurrentLocation,
                  icon: const Icon(Icons.my_location),
                  label: const Text('現在地を取得'),
                ),
                const SizedBox(width: 12),
                TextButton(
                  onPressed: _busy || !_mapReady
                      ? null
                      : () => _mapController.move(const LatLng(15, 0), 2.0),
                  child: const Text('世界全体'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: height,
              child: FlutterMap(
                mapController: _mapController,
                options: MapOptions(
                  initialCenter: _selected,
                  initialZoom: 10,
                  minZoom: 2,
                  maxZoom: 18,
                  onMapReady: () {
                    if (mounted) setState(() => _mapReady = true);
                  },
                  onTap: (_, point) => _setPoint(point),
                ),
                children: [
                  TileLayer(
                    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'jp.stellarium.neo',
                    maxZoom: 18,
                  ),
                  MarkerLayer(markers: [
                    Marker(
                      point: _selected,
                      width: 48,
                      height: 48,
                      child: const Icon(
                        Icons.location_pin,
                        color: Colors.redAccent,
                        size: 42,
                      ),
                    ),
                  ]),
                  RichAttributionWidget(attributions: [
                    TextSourceAttribution(
                      '© OpenStreetMap contributors',
                      onTap: () {
                        launchUrl(Uri.parse('https://www.openstreetmap.org/copyright'));
                      },
                    ),
                  ]),
                ],
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '緯度 ${_selected.latitude.toStringAsFixed(6)}° / '
              '経度 ${_selected.longitude.toStringAsFixed(6)}°',
            ),
            if (_locationAccuracy != null)
              Text(
                'Windowsによる現在地の推定誤差: '
                '約${_locationAccuracy!.toStringAsFixed(0)} m'
                '${_locationAccuracy! > 500 ? '（精度が低い可能性があります）' : ''}',
                style: const TextStyle(fontSize: 12),
              ),
            if (_error != null)
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            const Text(
              '地図をクリックして地点を指定。標高は「この地点を使用」で照会します。'
              '標高の照会時のみ選択した座標が外部サービスに送信されます。',
              style: TextStyle(fontSize: 12),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('キャンセル'),
        ),
        FilledButton.icon(
          onPressed: _busy ? null : _confirmPoint,
          icon: _busy
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.check),
          label: const Text('この地点を使用'),
        ),
      ],
    );
  }
}
