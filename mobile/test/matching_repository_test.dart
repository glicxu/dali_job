import 'dart:convert';

import 'package:dalijob_mobile/src/api/api_client.dart';
import 'package:dalijob_mobile/src/auth/auth_repository.dart';
import 'package:dalijob_mobile/src/auth/session_controller.dart';
import 'package:dalijob_mobile/src/auth/token_store.dart';
import 'package:dalijob_mobile/src/matching/matching_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _MemoryTokenStore implements RefreshTokenStore {
  String? token;

  @override
  Future<void> clear() async => token = null;

  @override
  Future<String?> read() async => token;

  @override
  Future<void> write(String value) async => token = value;
}

void main() {
  test('loads onboarding state from authenticated backend contracts', () async {
    final client = MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/auth/mobile/sessions')) {
        return _json({
          'access_token': 'access',
          'refresh_token': 'refresh',
          'user': {
            'external_user_id': '42',
            'email': 'person@example.com',
            'display_name': 'Person',
            'role': 'user',
          },
        }, 201);
      }
      expect(request.headers['authorization'], 'Bearer access');
      if (path.endsWith('/resume-profiles')) {
        return _json({'resume_profiles': <Object>[]});
      }
      if (path.endsWith('/job-search/criteria')) {
        return _json({'criteria': <Object>[]});
      }
      if (path.endsWith('/automation/schedules')) {
        return _json({'schedules': <Object>[]});
      }
      if (path.endsWith('/account/entitlements')) {
        return _json({
          'tier_code': 'free',
          'searches_per_period': 1,
          'searches_available': 1,
          'minimum_interval_minutes': 10080,
          'period_ends_at': '2026-08-21T00:00:00Z',
        });
      }
      return http.Response('not found', 404);
    });
    final api = ApiClient(Uri.parse('https://api.example.com/api/v1/'), client);
    final session = SessionController(
      repository: AuthRepository(api),
      tokenStore: _MemoryTokenStore(),
      deviceLabel: 'test device',
    );
    await session.signIn('person@example.com', 'password123');

    final snapshot = await MatchingRepository(api, session).loadOnboarding();

    expect(snapshot.profiles, isEmpty);
    expect(snapshot.criteria, isEmpty);
    expect(snapshot.schedules, isEmpty);
    expect(snapshot.entitlement.tierCode, 'free');
    expect(snapshot.entitlement.searchesAvailable, 1);
  });
}

http.Response _json(Map<String, dynamic> value, [int status = 200]) =>
    http.Response(
      jsonEncode(value),
      status,
      headers: {'content-type': 'application/json'},
    );
