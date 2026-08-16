import 'dart:convert';

import 'package:dalijob_mobile/src/api/api_client.dart';
import 'package:dalijob_mobile/src/auth/auth_repository.dart';
import 'package:dalijob_mobile/src/auth/session_controller.dart';
import 'package:dalijob_mobile/src/auth/token_store.dart';
import 'package:dalijob_mobile/src/features/evaluation/tester_evaluation_screen.dart';
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
  testWidgets(
    'tester lab exposes independent candidate, job, and matching sections',
    (tester) async {
      var candidateReviewSubmitted = false;
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/auth/mobile/sessions')) {
          return _json({
            'access_token': 'access',
            'refresh_token': 'refresh',
            'user': {
              'external_user_id': '42',
              'email': 'tester@example.com',
              'display_name': 'Tester',
              'role': 'admin',
            },
          }, 201);
        }
        if (request.url.path.endsWith('/internal/evaluation/fixture-catalog')) {
          return _json({
            'candidate_fixture_release': 'candidate-fixtures.synthetic.v1',
            'pair_release': 'pairs.v1',
            'benchmark_release': 'jobs.v1',
            'candidates': <Object>[],
            'pairs': <Object>[],
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/candidate-sources',
        )) {
          return _json({
            'candidates': [
              {
                'resume_profile_id': 23,
                'label': '[EVAL internal] Resume 23',
                'fixture_group': 'internal',
                'candidate_profile_id': 'cp_23',
                'profile_created_at': '2026-08-16T00:00:00Z',
              },
            ],
          });
        }
        if (request.url.path.endsWith('/internal/evaluation/job-snapshots')) {
          return _json({
            'snapshots': [
              {
                'public_id': 'ejs_1',
                'review_status': 'accepted',
                'company': 'Example',
                'title': 'Senior Engineer',
              },
            ],
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/candidate-sources/23/profile',
        )) {
          return _json({
            'resume_profile_id': 23,
            'resume_title': 'Resume 23',
            'resume_source': {
              'text': 'Built reliable APIs.',
              'spans': <Object>[],
            },
            'candidate_profile': {
              'candidate_profile_id': 'cp_23',
              'extracted': {
                'skills': ['Python'],
              },
            },
            'annotation_targets': <Object>[],
            'reviews': <Object>[],
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/job-snapshots/ejs_1/profile',
        )) {
          return _json({
            'job_snapshot_id': 'ejs_1',
            'job_title': 'Senior Engineer',
            'job_company': 'Example',
            'job_source': {'text': 'Build reliable APIs.', 'spans': <Object>[]},
            'job_profile': {
              'job_profile_id': 'jp_1',
              'requirements': ['Python'],
            },
            'annotation_targets': <Object>[],
            'reviews': <Object>[],
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/candidate-profiles/cp_23/reviews',
        )) {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          candidateReviewSubmitted = true;
          expect(body['overall_score'], 50);
          return _json({
            'public_id': 'evp_1',
            'stage': 'candidate_profile',
            'artifact_id': 'cp_23',
            'reviewer_user_id': 1,
            'reviewer_label': 'tester@example.com',
            ...body,
            'created_at': '2026-08-16T00:00:00Z',
          });
        }
        throw StateError('Unexpected request ${request.method} ${request.url}');
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
      await session.signIn('tester@example.com', 'password123');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TesterEvaluationScreen(
              repository: MatchingRepository(api, session),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('candidate_profile_lab')), findsOneWidget);
      expect(find.text('Candidate'), findsOneWidget);
      expect(find.text('Job'), findsOneWidget);
      expect(find.text('Matching'), findsOneWidget);
      expect(find.textContaining('Real ·'), findsOneWidget);

      await tester.tap(
        find.byKey(const Key('load_candidate_profile_evaluation')),
      );
      await tester.pumpAndSettle();
      expect(find.text('Resume source'), findsOneWidget);
      expect(find.text('Candidate Profile'), findsWidgets);

      await tester.ensureVisible(find.byType(TextField));
      await tester.enterText(find.byType(TextField), 'Accurate extraction.');
      await tester.pump();
      await tester.ensureVisible(
        find.byKey(const Key('submit_candidate_profile_review')),
      );
      final submit = tester.widget<FilledButton>(
        find.byKey(const Key('submit_candidate_profile_review')),
      );
      expect(submit.onPressed, isNotNull);
      submit.onPressed!();
      await tester.pumpAndSettle();
      expect(candidateReviewSubmitted, isTrue);

      await tester.fling(find.byType(ListView), const Offset(0, 1000), 1000);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Job'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('job_profile_lab')), findsOneWidget);
      await tester.tap(find.byKey(const Key('load_job_profile_evaluation')));
      await tester.pumpAndSettle();
      expect(find.text('Job description source'), findsOneWidget);

      await tester.fling(find.byType(ListView), const Offset(0, 1000), 1000);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Matching'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('matching_lab')), findsOneWidget);
    },
  );
}

http.Response _json(Map<String, dynamic> value, [int status = 200]) =>
    http.Response(
      jsonEncode(value),
      status,
      headers: {'content-type': 'application/json'},
    );
