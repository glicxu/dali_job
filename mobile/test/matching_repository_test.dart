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

  test('loads owned match snapshots and sends user feedback', () async {
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
      if (path.endsWith('/match-inbox') && request.method == 'GET') {
        return _json({
          'items': [
            {
              'match_id': 7,
              'search_schedule_id': 3,
              'title': 'Backend Engineer',
              'company': 'Example',
              'match_score': 8,
              'status': 'read',
              'match_data': {'summary': 'Strong overlap'},
              'resume_data': {'headline': 'Senior Engineer'},
              'job_data': {'title': 'Backend Engineer'},
              'created_at': '2026-08-16T12:00:00Z',
              'source_url': null,
              'user_feedback': null,
              'matching_v2_result': {
                'match_id': 'match_v2_7',
                'qualification_assessment_id': 'qa_7',
                'preference_assessment_id': null,
                'eligibility_assessment_id': null,
                'scores': {
                  'qualification_score': null,
                  'diagnostic_qualification_score': 72,
                  'qualification_coverage': 0.65,
                  'preference_score': null,
                  'preference_coverage': null,
                  'preference_state': 'not_configured',
                  'overall_score': null,
                  'recommendation': 'needs_more_information',
                  'gates': <Object>[],
                  'reason_codes': ['QUALIFICATION_COVERAGE_BELOW_THRESHOLD'],
                  'questions': ['Can you confirm your systems experience?'],
                },
                'explanation': {
                  'summary': 'More information is needed.',
                  'strengths': [
                    {
                      'key': 'req_1',
                      'label': 'Python',
                      'detail': 'Demonstrated in recent work.',
                      'evidence_refs': ['private_span_1'],
                    },
                  ],
                  'gaps': <Object>[],
                  'unknowns': <Object>[],
                  'preference_conflicts': <Object>[],
                  'questions': <Object>[],
                },
                'policy': {'scoring': 'score.v1'},
                'legacy_score': null,
                'created_at': '2026-08-16T12:00:00Z',
              },
            },
          ],
          'next_cursor': null,
        });
      }
      if (path.endsWith('/match-inbox/7/feedback') && request.method == 'PUT') {
        expect(jsonDecode(request.body)['score'], 75);
        return _json({
          'score': 75,
          'recommendation': 'good_match',
          'rationale': 'Relevant role',
          'created_at': '2026-08-16T12:01:00Z',
          'updated_at': '2026-08-16T12:01:00Z',
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
    final repository = MatchingRepository(api, session);

    final matches = await repository.listMatches();
    final feedback = await repository.putMatchFeedback(
      matchId: 7,
      score: 75,
      rationale: 'Relevant role',
    );

    expect(matches.single.resumeData['headline'], 'Senior Engineer');
    expect(matches.single.jobData['title'], 'Backend Engineer');
    expect(matches.single.v2Result?.scores.overallScore, isNull);
    expect(matches.single.needsMoreInformation, isTrue);
    expect(
      matches.single.v2Result?.explanation.strengths.single.label,
      'Python',
    );
    expect(feedback.recommendation, 'good_match');
  });

  test(
    'refreshes nullable preferences and sends revision-controlled updates',
    () async {
      var readCount = 0;
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
        if (path.endsWith('/users/me/matching-preferences') &&
            request.method == 'GET') {
          readCount += 1;
          return readCount == 1
              ? http.Response(
                  'null',
                  200,
                  headers: {'content-type': 'application/json'},
                )
              : _json({'revision': 2, 'preferences': _preferenceFixture()});
        }
        if (path.endsWith('/users/me/matching-preferences') &&
            request.method == 'PUT') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['expected_revision'], 0);
          return _json({
            'revision': 1,
            'preferences': body['preferences'] as Map<String, dynamic>,
          });
        }
        return http.Response('not found', 404);
      });
      final api = ApiClient(
        Uri.parse('https://api.example.com/api/v1/'),
        client,
      );
      final session = SessionController(
        repository: AuthRepository(api),
        tokenStore: _MemoryTokenStore(),
        deviceLabel: 'test device',
      );
      await session.signIn('person@example.com', 'password123');
      final repository = MatchingRepository(api, session);

      expect(await repository.getPreferences(), isNull);
      final saved = await repository.putPreferences(
        expectedRevision: 0,
        preferences: _preferenceFixture(),
      );
      expect(saved.revision, 1);
      expect((await repository.getPreferences())?.revision, 2);
    },
  );
}

Map<String, dynamic> _preferenceFixture() => {
  'desired_roles': <Object>[],
  'locations': null,
  'workplace_types': <Object>[],
  'compensation': null,
  'employment_types': null,
  'desired_skills': <Object>[],
  'avoided_industries': <Object>[],
  'hard_constraints': <Object>[],
};

http.Response _json(Map<String, dynamic> value, [int status = 200]) =>
    http.Response(
      jsonEncode(value),
      status,
      headers: {'content-type': 'application/json'},
    );
