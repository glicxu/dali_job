import 'dart:io';

import 'package:flutter/foundation.dart';

class AppEnvironment {
  const AppEnvironment({required this.name, required this.apiBaseUrl});

  final String name;
  final Uri apiBaseUrl;

  factory AppEnvironment.fromDefines() {
    const name = String.fromEnvironment(
      'DALIJOB_ENV',
      defaultValue: 'development',
    );
    const configuredUrl = String.fromEnvironment('DALIJOB_API_BASE_URL');
    final fallback = Platform.isAndroid
        ? 'http://10.0.2.2:5010/api/v1/'
        : 'http://127.0.0.1:5010/api/v1/';
    final url = Uri.parse(configuredUrl.isEmpty ? fallback : configuredUrl);
    if (!url.hasScheme || !url.path.endsWith('/')) {
      throw StateError(
        'DALIJOB_API_BASE_URL must be an absolute URL ending in /.',
      );
    }
    if (kReleaseMode && url.scheme != 'https') {
      throw StateError('Release builds require an HTTPS API URL.');
    }
    return AppEnvironment(name: name, apiBaseUrl: url);
  }
}
