import 'package:flutter/material.dart';

import '../services/api_service.dart';

enum DisplayMode { orbitalElements, radec }

enum InputTimeZone { jst, utc }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _apiService = ApiService();
  final TextEditingController _targetController = TextEditingController();

  bool _isCheckingBackend = false;
  bool? _backendConnected;
  String _backendStatusMessage = '未接続';

  bool _isInspectingTarget = false;
  TargetInfo? _targetInfo;
  String? _targetError;

  DisplayMode _displayMode = DisplayMode.orbitalElements;
  InputTimeZone _timeZone = InputTimeZone.jst;

  late DateTime _orbitReferenceDateTime;
  late DateTime _radecStartDateTime;
  late DateTime _radecEndDateTime;

  String _observerName = '松江高専';
  double _observerLatitude = 35.4978;
  double _observerLongitude = 133.025;
  double _observerAltitude = 0.0;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    final rounded = DateTime(now.year, now.month, now.day, now.hour);
    _orbitReferenceDateTime = rounded;
    _radecStartDateTime = rounded;
    _radecEndDateTime = rounded.add(const Duration(hours: 4));

    Future.microtask(_checkBackend);
  }

  @override
  void dispose() {
    _targetController.dispose();
    super.dispose();
  }

  Future<void> _checkBackend() async {
    if (_isCheckingBackend) {
      return;
    }

    setState(() {
      _isCheckingBackend = true;
      _backendStatusMessage = '確認中...';
    });

    try {
      final message = await _apiService.checkStatus();
      if (!mounted) {
        return;
      }
      setState(() {
        _backendConnected = true;
        _backendStatusMessage = message;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _backendConnected = false;
        _backendStatusMessage = _cleanException(error);
      });
    } finally {
      if (mounted) {
        setState(() {
          _isCheckingBackend = false;
        });
      }
    }
  }

  Future<void> _inspectTarget() async {
    final identifier = _targetController.text.trim();
    if (identifier.isEmpty || _isInspectingTarget) {
      setState(() {
        _targetError = identifier.isEmpty ? '天体を入力してください。' : null;
      });
      return;
    }

    setState(() {
      _isInspectingTarget = true;
      _targetError = null;
      _targetInfo = null;
    });

    try {
      final result = await _apiService.inspectTarget(identifier);
      if (!mounted) {
        return;
      }
      setState(() {
        _targetInfo = result;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _targetError = _cleanException(error);
      });
    } finally {
      if (mounted) {
        setState(() {
          _isInspectingTarget = false;
        });
      }
    }
  }

  Future<DateTime?> _pickDateTime(DateTime current) async {
    final date = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(1900),
      lastDate: DateTime(2200),
    );
    if (date == null || !mounted) {
      return null;
    }

    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
    );
    if (time == null) {
      return null;
    }

    return DateTime(date.year, date.month, date.day, time.hour, time.minute);
  }

  Future<void> _editObserver() async {
    final result = await showDialog<_ObserverDraft>(
      context: context,
      builder: (context) {
        final formKey = GlobalKey<FormState>();
        final nameController = TextEditingController(text: _observerName);
        final latitudeController = TextEditingController(
          text: _observerLatitude.toString(),
        );
        final longitudeController = TextEditingController(
          text: _observerLongitude.toString(),
        );
        final altitudeController = TextEditingController(
          text: _observerAltitude.toString(),
        );

        String? validateNumber(
          String? value,
          String label,
          double min,
          double max,
        ) {
          final number = double.tryParse(value?.trim() ?? '');
          if (number == null) {
            return '$labelを数値で入力してください。';
          }
          if (number < min || number > max) {
            return '$labelは $min 〜 $max の範囲で入力してください。';
          }
          return null;
        }

        return AlertDialog(
          title: const Text('観測地点を変更'),
          content: SizedBox(
            width: 480,
            child: Form(
              key: formKey,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextFormField(
                      controller: nameController,
                      decoration: const InputDecoration(
                        labelText: '地点名',
                        hintText: '例: 松江高専',
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: latitudeController,
                      decoration: const InputDecoration(
                        labelText: '緯度 [deg]',
                      ),
                      validator: (value) =>
                          validateNumber(value, '緯度', -90, 90),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: longitudeController,
                      decoration: const InputDecoration(
                        labelText: '経度 [deg]',
                      ),
                      validator: (value) =>
                          validateNumber(value, '経度', -180, 180),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: altitudeController,
                      decoration: const InputDecoration(
                        labelText: '標高 [m]',
                      ),
                      validator: (value) {
                        if (double.tryParse(value?.trim() ?? '') == null) {
                          return '標高を数値で入力してください。';
                        }
                        return null;
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('キャンセル'),
            ),
            FilledButton(
              onPressed: () {
                if (!(formKey.currentState?.validate() ?? false)) {
                  return;
                }
                Navigator.of(context).pop(
                  _ObserverDraft(
                    name: nameController.text.trim().isEmpty
                        ? 'Custom observer'
                        : nameController.text.trim(),
                    latitude: double.parse(latitudeController.text.trim()),
                    longitude: double.parse(longitudeController.text.trim()),
                    altitude: double.parse(altitudeController.text.trim()),
                  ),
                );
              },
              child: const Text('保存'),
            ),
          ],
        );
      },
    );

    if (result == null || !mounted) {
      return;
    }

    setState(() {
      _observerName = result.name;
      _observerLatitude = result.latitude;
      _observerLongitude = result.longitude;
      _observerAltitude = result.altitude;
    });
  }

  void _setTimeZone(InputTimeZone nextZone) {
    if (nextZone == _timeZone) {
      return;
    }

    final offset = nextZone == InputTimeZone.utc
        ? const Duration(hours: -9)
        : const Duration(hours: 9);

    setState(() {
      _orbitReferenceDateTime = _orbitReferenceDateTime.add(offset);
      _radecStartDateTime = _radecStartDateTime.add(offset);
      _radecEndDateTime = _radecEndDateTime.add(offset);
      _timeZone = nextZone;
    });
  }

  void _showPendingAction(String actionName) {
    final message = _targetInfo == null
        ? '先に天体を検索して確定してください。'
        : '$actionName は次のAPI接続工程で実装します。';

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 48,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: _BackendStatusChip(
              isChecking: _isCheckingBackend,
              connected: _backendConnected,
              message: _backendStatusMessage,
              onPressed: _checkBackend,
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1180),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _SectionCard(
                        step: '1',
                        title: '天体を選択',
                        child: _buildTargetSection(),
                      ),
                      const SizedBox(height: 12),
                      _SectionCard(
                        step: '2',
                        title: '表示方式を選択',
                        child: _buildModeSection(),
                      ),
                      const SizedBox(height: 12),
                      _SectionCard(
                        step: '3',
                        title: '条件を設定',
                        child: AnimatedSwitcher(
                          duration: const Duration(milliseconds: 180),
                          child: _displayMode == DisplayMode.orbitalElements
                              ? _buildOrbitalConditionSection()
                              : _buildRaDecConditionSection(),
                        ),
                      ),
                      const SizedBox(height: 12),
                      _SectionCard(
                        step: '4',
                        title: '実行',
                        child: _buildActionSection(),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildTargetSection() {
    final targetInfo = _targetInfo;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LayoutBuilder(
          builder: (context, constraints) {
            final narrow = constraints.maxWidth < 680;
            final input = TextField(
              controller: _targetController,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _inspectTarget(),
              decoration: InputDecoration(
                labelText: '天体',
                hintText: '例: 99942 / Apophis / 2004 MN4 / 2099942 / アポフィス',
                prefixIcon: const Icon(Icons.public),
                errorText: _targetError,
              ),
            );
            final button = FilledButton.icon(
              onPressed: _isInspectingTarget ? null : _inspectTarget,
              icon: _isInspectingTarget
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.search),
              label: Text(_isInspectingTarget ? '確認中' : 'JPLで検索'),
            );

            if (narrow) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  input,
                  const SizedBox(height: 12),
                  SizedBox(height: 50, child: button),
                ],
              );
            }

            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: input),
                const SizedBox(width: 10),
                SizedBox(height: 56, child: button),
              ],
            );
          },
        ),
        if (targetInfo != null) ...[
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Theme.of(context)
                  .colorScheme
                  .primaryContainer
                  .withValues(alpha: 0.18),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: Theme.of(context)
                    .colorScheme
                    .primary
                    .withValues(alpha: 0.35),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.check_circle,
                      color: Theme.of(context).colorScheme.primary,
                      size: 20,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        targetInfo.fullName,
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    _InfoPill(
                      label: targetInfo.isRegistered
                          ? 'JPL版登録済み'
                          : '未登録',
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    _LabeledValue(
                      label: '主識別子',
                      value: targetInfo.primaryDesignation,
                    ),
                    _LabeledValue(
                      label: '小惑星番号',
                      value: targetInfo.minorPlanetNumber ?? '—',
                    ),
                    _LabeledValue(
                      label: '仮符号',
                      value: targetInfo.iauDesignation ?? '—',
                    ),
                    _LabeledValue(
                      label: 'SPK-ID',
                      value: targetInfo.spkId.isEmpty ? '—' : targetInfo.spkId,
                    ),
                    _LabeledValue(
                      label: 'Horizons',
                      value: targetInfo.horizonsCommand,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildModeSection() {
    return SegmentedButton<DisplayMode>(
      segments: const [
        ButtonSegment(
          value: DisplayMode.orbitalElements,
          icon: Icon(Icons.route),
          label: Text('軌道要素'),
        ),
        ButtonSegment(
          value: DisplayMode.radec,
          icon: Icon(Icons.my_location),
          label: Text('RA / Dec'),
        ),
      ],
      selected: {_displayMode},
      onSelectionChanged: (selection) {
        setState(() {
          _displayMode = selection.first;
        });
      },
    );
  }

  Widget _buildOrbitalConditionSection() {
    return Column(
      key: const ValueKey('orbital-conditions'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: 14,
          runSpacing: 14,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 360,
              child: _DateTimeField(
                label: '基準日時',
                value: _formatDateTime(_orbitReferenceDateTime),
                onPressed: () async {
                  final picked = await _pickDateTime(_orbitReferenceDateTime);
                  if (picked != null && mounted) {
                    setState(() {
                      _orbitReferenceDateTime = picked;
                    });
                  }
                },
              ),
            ),
            SegmentedButton<InputTimeZone>(
              segments: const [
                ButtonSegment(value: InputTimeZone.jst, label: Text('JST')),
                ButtonSegment(value: InputTimeZone.utc, label: Text('UTC')),
              ],
              selected: {_timeZone},
              onSelectionChanged: (selection) {
                _setTimeZone(selection.first);
              },
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildRaDecConditionSection() {
    final duration = _radecEndDateTime.difference(_radecStartDateTime);
    final validOrder = duration > Duration.zero;
    final withinLimit = duration <= const Duration(hours: 12);
    final pointCount = validOrder
        ? (duration.inMilliseconds / 500).floor() + 1
        : 0;

    return Column(
      key: const ValueKey('radec-conditions'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.025),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: Row(
            children: [
              const Icon(Icons.location_on_outlined),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _observerName,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '緯度 ${_observerLatitude.toStringAsFixed(4)}° / '
                      '経度 ${_observerLongitude.toStringAsFixed(4)}° / '
                      '標高 ${_observerAltitude.toStringAsFixed(0)} m',
                      style: TextStyle(
                        color: Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withValues(alpha: 0.70),
                      ),
                    ),
                  ],
                ),
              ),
              OutlinedButton.icon(
                onPressed: _editObserver,
                icon: const Icon(Icons.edit_location_alt_outlined),
                label: const Text('変更'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        Align(
          alignment: Alignment.centerLeft,
          child: SegmentedButton<InputTimeZone>(
            segments: const [
              ButtonSegment(value: InputTimeZone.jst, label: Text('JST')),
              ButtonSegment(value: InputTimeZone.utc, label: Text('UTC')),
            ],
            selected: {_timeZone},
            onSelectionChanged: (selection) {
              _setTimeZone(selection.first);
            },
          ),
        ),
        const SizedBox(height: 14),
        LayoutBuilder(
          builder: (context, constraints) {
            final narrow = constraints.maxWidth < 760;
            final start = _DateTimeField(
              label: '開始日時',
              value: _formatDateTime(_radecStartDateTime),
              onPressed: () async {
                final picked = await _pickDateTime(_radecStartDateTime);
                if (picked != null && mounted) {
                  setState(() {
                    _radecStartDateTime = picked;
                  });
                }
              },
            );
            final end = _DateTimeField(
              label: '終了日時',
              value: _formatDateTime(_radecEndDateTime),
              onPressed: () async {
                final picked = await _pickDateTime(_radecEndDateTime);
                if (picked != null && mounted) {
                  setState(() {
                    _radecEndDateTime = picked;
                  });
                }
              },
            );

            if (narrow) {
              return Column(
                children: [
                  start,
                  const SizedBox(height: 12),
                  end,
                ],
              );
            }

            return Row(
              children: [
                Expanded(child: start),
                const SizedBox(width: 10),
                Expanded(child: end),
              ],
            );
          },
        ),
        const SizedBox(height: 14),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            const _LabeledValue(label: '取得間隔', value: '0.5 秒（固定）'),
            _LabeledValue(
              label: '取得時間',
              value: validOrder ? _formatDuration(duration) : '無効',
            ),
            _LabeledValue(
              label: '取得点数の目安',
              value: validOrder ? '$pointCount 点' : '—',
            ),
          ],
        ),
        if (!validOrder) ...[
          const SizedBox(height: 12),
          const _InlineNote(
            icon: Icons.error_outline,
            text: '終了日時は開始日時より後にしてください。',
            isError: true,
          ),
        ] else if (!withinLimit) ...[
          const SizedBox(height: 12),
          const _InlineNote(
            icon: Icons.warning_amber_rounded,
            text: '現在のPython側ではRA/Dec取得範囲は最大12時間です。',
            isError: true,
          ),
        ],
      ],
    );
  }

  Widget _buildActionSection() {
    final canProceed = _targetInfo != null;
    final isRaDec = _displayMode == DisplayMode.radec;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LayoutBuilder(
          builder: (context, constraints) {
            final narrow = constraints.maxWidth < 620;
            final fetchButton = FilledButton.icon(
              onPressed: canProceed
                  ? () => _showPendingAction(
                        isRaDec ? 'JPL RA/Dec取得' : 'JPL軌道要素取得',
                      )
                  : null,
              icon: const Icon(Icons.cloud_download_outlined),
              label: Text(isRaDec ? 'JPLからRA/Decを取得' : 'JPLから軌道要素を取得'),
            );
            final displayButton = OutlinedButton.icon(
              onPressed: canProceed
                  ? () => _showPendingAction('Stellarium表示')
                  : null,
              icon: const Icon(Icons.open_in_new),
              label: const Text('Stellariumへ表示'),
            );

            if (narrow) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SizedBox(height: 52, child: fetchButton),
                  const SizedBox(height: 10),
                  SizedBox(height: 52, child: displayButton),
                ],
              );
            }

            return Row(
              children: [
                Expanded(child: SizedBox(height: 52, child: fetchButton)),
                const SizedBox(width: 10),
                Expanded(child: SizedBox(height: 52, child: displayButton)),
              ],
            );
          },
        ),
      ],
    );
  }

  String _formatDateTime(DateTime value) {
    return '${value.year}/${_pad2(value.month)}/${_pad2(value.day)} '
        '${_pad2(value.hour)}:${_pad2(value.minute)} '
        '${_timeZone == InputTimeZone.jst ? 'JST' : 'UTC'}';
  }

  String _formatDuration(Duration duration) {
    final hours = duration.inHours;
    final minutes = duration.inMinutes.remainder(60);
    if (minutes == 0) {
      return '$hours 時間';
    }
    return '$hours 時間 $minutes 分';
  }

  String _pad2(int value) => value.toString().padLeft(2, '0');

  String _cleanException(Object error) {
    return error.toString().replaceFirst('Exception: ', '');
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.step,
    required this.title,
    required this.child,
  });

  final String step;
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.white.withValues(alpha: 0.07)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 32,
                  height: 32,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.16),
                    shape: BoxShape.circle,
                  ),
                  child: Text(
                    step,
                    style: TextStyle(
                      color: theme.colorScheme.primary,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            child,
          ],
        ),
      ),
    );
  }
}

class _BackendStatusChip extends StatelessWidget {
  const _BackendStatusChip({
    required this.isChecking,
    required this.connected,
    required this.message,
    required this.onPressed,
  });

  final bool isChecking;
  final bool? connected;
  final String message;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final color = isChecking
        ? Theme.of(context).colorScheme.primary
        : connected == true
            ? Colors.greenAccent
            : connected == false
                ? Colors.redAccent
                : Colors.white70;

    return Tooltip(
      message: message,
      child: TextButton.icon(
        onPressed: isChecking ? null : onPressed,
        icon: isChecking
            ? const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(Icons.circle, size: 10, color: color),
        label: Text(
          connected == true
              ? 'Backend 接続済み'
              : connected == false
                  ? 'Backend 未接続'
                  : 'Backend 確認',
        ),
      ),
    );
  }
}

class _DateTimeField extends StatelessWidget {
  const _DateTimeField({
    required this.label,
    required this.value,
    required this.onPressed,
  });

  final String label;
  final String value;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(12),
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: const Icon(Icons.calendar_month_outlined),
          suffixIcon: const Icon(Icons.edit_calendar_outlined),
        ),
        child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
      ),
    );
  }
}

class _LabeledValue extends StatelessWidget {
  const _LabeledValue({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(10),
      ),
      child: RichText(
        text: TextSpan(
          style: DefaultTextStyle.of(context).style,
          children: [
            TextSpan(
              text: '$label  ',
              style: TextStyle(
                color: Theme.of(context)
                    .colorScheme
                    .onSurface
                    .withValues(alpha: 0.55),
              ),
            ),
            TextSpan(
              text: value,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoPill extends StatelessWidget {
  const _InfoPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: Theme.of(context).colorScheme.primary,
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _InlineNote extends StatelessWidget {
  const _InlineNote({
    required this.icon,
    required this.text,
    this.isError = false,
  });

  final IconData icon;
  final String text;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    final color = isError
        ? Theme.of(context).colorScheme.error
        : Theme.of(context).colorScheme.primary;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 19, color: color),
          const SizedBox(width: 9),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}

class _ObserverDraft {
  const _ObserverDraft({
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
