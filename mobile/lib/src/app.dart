import 'package:flutter/material.dart';

import 'auth/session_controller.dart';
import 'config/app_environment.dart';
import 'features/auth/auth_screen.dart';
import 'features/home/home_screen.dart';

class DaliJobApp extends StatelessWidget {
  const DaliJobApp({
    super.key,
    required this.environment,
    required this.session,
  });

  final AppEnvironment environment;
  final SessionController session;

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'DaliJob',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xff235347),
        brightness: Brightness.light,
      ),
      useMaterial3: true,
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
    ),
    home: ListenableBuilder(
      listenable: session,
      builder: (context, _) => switch (session.status) {
        SessionStatus.bootstrapping => const _BootstrapScreen(),
        SessionStatus.anonymous => AuthScreen(session: session),
        SessionStatus.authenticated => HomeScreen(
          session: session,
          environment: environment,
        ),
      },
    ),
  );
}

class _BootstrapScreen extends StatelessWidget {
  const _BootstrapScreen();

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator()));
}
