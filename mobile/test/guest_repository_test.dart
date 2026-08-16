import 'dart:convert';

import 'package:dalijob_mobile/src/api/api_client.dart';
import 'package:dalijob_mobile/src/guest/guest_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test(
    'guest repository uses distinct Guest authorization and idempotency',
    () async {
      final requests = <http.Request>[];
      final repository = GuestRepository(
        ApiClient(
          Uri.parse('https://api.example.com/api/v1/'),
          MockClient((request) async {
            requests.add(request);
            if (request.url.path.endsWith('/match')) {
              return http.Response(
                jsonEncode({
                  'operation_id': 1,
                  'status': 'result_ready',
                  'provider_search_state': 'consumed',
                  'result': {
                    'title': 'Backend Engineer',
                    'company': 'Example',
                    'match_score': 9,
                    'summary': 'Strong fit',
                  },
                }),
                200,
              );
            }
            return http.Response('{}', 200);
          }),
        ),
      );

      final result = await repository.startMatch('public.secret', 'stable-key');
      final status = await repository.matchStatus('public.secret');

      expect(result['status'], 'result_ready');
      expect(status['status'], 'result_ready');
      expect(requests.first.headers['Authorization'], 'Guest public.secret');
      expect(requests.first.headers['Idempotency-Key'], 'stable-key');
      expect(requests.last.method, 'GET');
      expect(
        requests.first.headers['Authorization'],
        isNot(startsWith('Bearer')),
      );
    },
  );

  test('guest current combines restored trial and match state', () async {
    final repository = GuestRepository(
      ApiClient(
        Uri.parse('https://api.example.com/api/v1/'),
        MockClient((request) async {
          if (request.url.path.endsWith('/current/match')) {
            return http.Response(
              '{"operation_id":null,"status":"not_started","provider_search_state":"available"}',
              200,
            );
          }
          return http.Response(
            '{"public_id":"trial","status":"active","provider_search_state":"available","profile":null,"criteria":null,"resume_import":null}',
            200,
          );
        }),
      ),
    );

    final restored = await repository.current('trial.secret');
    expect(restored.publicId, 'trial');
    expect(restored.match?['status'], 'not_started');
  });
}
