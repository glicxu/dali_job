import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'src/api/api_client.dart';
import 'src/app.dart';
import 'src/auth/auth_repository.dart';
import 'src/auth/session_controller.dart';
import 'src/auth/token_store.dart';
import 'src/config/app_environment.dart';
import 'src/guest/guest_controller.dart';
import 'src/guest/guest_repository.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final environment = AppEnvironment.fromDefines();
  final api = ApiClient(environment.apiBaseUrl, http.Client());
  const secureStorage = FlutterSecureStorage();
  final controller = SessionController(
    repository: AuthRepository(api),
    tokenStore: const FlutterSecureTokenStore(secureStorage),
    deviceLabel: '${Platform.operatingSystem} device',
  );
  final guest = GuestController(
    repository: GuestRepository(api),
    credentialStore: const FlutterSecureGuestCredentialStore(secureStorage),
  );
  runApp(
    DaliJobApp(environment: environment, session: controller, guest: guest),
  );
  controller.bootstrap();
  guest.bootstrap();
}
