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

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final environment = AppEnvironment.fromDefines();
  final controller = SessionController(
    repository: AuthRepository(
      ApiClient(environment.apiBaseUrl, http.Client()),
    ),
    tokenStore: const FlutterSecureTokenStore(FlutterSecureStorage()),
    deviceLabel: '${Platform.operatingSystem} device',
  );
  runApp(DaliJobApp(environment: environment, session: controller));
  controller.bootstrap();
}
