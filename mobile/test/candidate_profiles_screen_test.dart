import 'dart:convert';

import 'package:dalijob_mobile/src/api/api_client.dart';
import 'package:dalijob_mobile/src/auth/auth_repository.dart';
import 'package:dalijob_mobile/src/auth/session_controller.dart';
import 'package:dalijob_mobile/src/auth/token_store.dart';
import 'package:dalijob_mobile/src/features/profile/candidate_profiles_screen.dart';
import 'package:dalijob_mobile/src/matching/matching_repository.dart';
import 'package:flutter/material.dart';
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
  testWidgets('lists and opens the current candidate profile', (tester) async {
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/auth/mobile/sessions')) {
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
      if (request.url.path.endsWith('/resume-profiles')) {
        expect(request.headers['authorization'], 'Bearer access');
        return _json({
          'resume_profiles': [
            {
              'id': 7,
              'title': 'Master Resume',
              'is_default': true,
              'resume_data': {
                'headline': 'Senior Software Engineer',
                'summary': 'Builds reliable distributed systems.',
                'skills': ['Python', 'System design'],
                'experience': ['Led delivery of a production platform.'],
                'projects': <String>[],
                'education': <String>[],
                'certifications': <String>[],
                'publications': <String>[],
                'awards': <String>[],
                'languages': <String>[],
                'volunteer': <String>[],
                'target_roles': ['Senior Software Engineer'],
                'notes': <String>[],
              },
            },
          ],
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

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CandidateProfilesScreen(
            repository: MatchingRepository(api, session),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('candidate_profiles_screen')), findsOneWidget);
    expect(find.text('Master Resume'), findsOneWidget);
    expect(find.text('Default'), findsOneWidget);
    expect(find.text('Senior Software Engineer'), findsOneWidget);

    await tester.tap(find.byKey(const Key('candidate_profile_7')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('candidate_profile_details')), findsOneWidget);
    expect(find.text('Builds reliable distributed systems.'), findsOneWidget);
    expect(find.text('Target roles'), findsOneWidget);
    expect(find.text('Skills'), findsOneWidget);
    expect(find.text('Python'), findsOneWidget);
    expect(find.text('Led delivery of a production platform.'), findsOneWidget);
  });
}

http.Response _json(Map<String, dynamic> value, [int status = 200]) =>
    http.Response(
      jsonEncode(value),
      status,
      headers: {'content-type': 'application/json'},
    );
