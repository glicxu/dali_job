import 'dart:convert';

import 'package:dalijob_mobile/src/api/api_client.dart';
import 'package:dalijob_mobile/src/auth/auth_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('mobile sign-in sends the device label and parses tokens', () async {
    late http.Request captured;
    final repository = AuthRepository(
      ApiClient(
        Uri.parse('https://api.example.com/api/v1/'),
        MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode({
              'access_token': 'access',
              'refresh_token': 'refresh',
              'user': {
                'external_user_id': '42',
                'email': 'person@example.com',
                'display_name': 'Person',
                'role': 'user',
              },
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }),
      ),
    );

    final pair = await repository.signIn(
      email: ' person@example.com ',
      password: 'password123',
      deviceLabel: 'android device',
    );

    expect(captured.url.path, '/api/v1/auth/mobile/sessions');
    expect(jsonDecode(captured.body)['device_label'], 'android device');
    expect(pair.refreshToken, 'refresh');
    expect(pair.user.displayName, 'Person');
  });

  test('password reset uses the existing backend route', () async {
    late http.Request captured;
    final repository = AuthRepository(
      ApiClient(
        Uri.parse('https://api.example.com/api/v1/'),
        MockClient((request) async {
          captured = request;
          return http.Response('{"message":"Check your email."}', 200);
        }),
      ),
    );

    expect(
      await repository.requestPasswordReset('person@example.com'),
      'Check your email.',
    );
    expect(captured.url.path, '/api/v1/auth/forgot-password');
  });
}
