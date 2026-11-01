import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:stellarium_neo_gui/screens/home_screen.dart';

void main() {
  testWidgets('表示方式の選択画面が表示される', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: HomeScreen(),
      ),
    );

    expect(find.text('通常精度'), findsOneWidget);
    expect(find.text('高精度'), findsOneWidget);
  });
}