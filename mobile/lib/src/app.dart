import 'package:flutter/material.dart';

import 'auth/session_controller.dart';
import 'config/app_environment.dart';
import 'features/auth/auth_screen.dart';
import 'features/home/home_screen.dart';
import 'features/guest/guest_trial_screen.dart';
import 'guest/guest_controller.dart';

class DaliJobApp extends StatelessWidget {
  const DaliJobApp({
    super.key,
    required this.environment,
    required this.session,
    required this.guest,
  });

  final AppEnvironment environment;
  final SessionController session;
  final GuestController guest;

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
      listenable: Listenable.merge([session, guest]),
      builder: (context, _) => switch (session.status) {
        SessionStatus.bootstrapping => const _BootstrapScreen(),
        SessionStatus.anonymous => switch (guest.status) {
          GuestStatus.bootstrapping => const _BootstrapScreen(),
          GuestStatus.active => GuestTrialScreen(controller: guest),
          GuestStatus.none => AuthScreen(
            session: session,
            initiallyRegistering: guest.preferRegistration,
            onTryMatch: guest.start,
            onResumeTrial: guest.credential == null ? null : guest.resumeTrial,
            tryBusy: guest.busy,
            tryError: guest.error,
          ),
        },
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
